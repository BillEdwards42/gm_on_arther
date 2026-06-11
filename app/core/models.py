import torch.nn as nn

class PureEncoderWithAttention(nn.Module):
    """
    Exact replica of the training architecture.
    Do not modify defaults unless retraining the model.
    """
    def __init__(self, input_dim, d_model=512, n_heads=8, n_targets=13, look_ahead=144, dropout=0.2, num_layers=5):
        super().__init__()
        self.look_ahead = look_ahead
        self.n_targets = n_targets
        d_ff = 4 * d_model 
        
        self.input_proj = nn.Linear(input_dim, d_model)
        self.encoder = nn.LSTM(d_model, d_model, batch_first=True, num_layers=num_layers, dropout=dropout)
        self.norm_enc = nn.LayerNorm(d_model)

        self.self_attn = nn.MultiheadAttention(d_model, n_heads, batch_first=True, dropout=dropout)
        self.norm_attn = nn.LayerNorm(d_model)

        self.ff = nn.Sequential(
            nn.Linear(d_model, d_ff),
            nn.ReLU(),
            nn.Dropout(dropout), 
            nn.Linear(d_ff, d_model)
        )
        self.norm_ff = nn.LayerNorm(d_model)
        self.amount_head = nn.Linear(d_model, n_targets * look_ahead)
        self.output_activation = nn.ReLU() 

    def forward(self, enc_x):
        enc = self.input_proj(enc_x)
        enc_out, (h_n, c_n) = self.encoder(enc)
        enc_out = self.norm_enc(enc_out)

        final_h = h_n[-1].unsqueeze(1)
        attn_out, _ = self.self_attn(query=final_h, key=enc_out, value=enc_out)

        x = self.norm_attn(attn_out + final_h)
        x = self.norm_ff(self.ff(x) + x) 
        x = x.squeeze(1)
        
        amt_flat = self.amount_head(x)
        target_shape = (-1, self.look_ahead, self.n_targets)
        return self.output_activation(amt_flat.view(target_shape))