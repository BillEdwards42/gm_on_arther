# app/services/ml_inference.py
import torch
import torch.nn as nn
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from typing import Dict, List, Optional

# Logging and Config
from app.core.logging import logger
from app.schemas.ml_cache import RegionDataRow

# ============================================================
# === 1. The Core Architecture (Immutable) ===
# ============================================================
class PureEncoderWithAttention(nn.Module):
    """
    Exact replica of the training architecture.
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


# ============================================================
# === 2. The Service Layer (The Integration Logic) ===
# ============================================================
class MLInferenceService:
    """
    The 'Mathematician'. 
    - Loads baked-in artifacts (Scalers/Models) on startup.
    - Accepts clean Pydantic objects.
    - Returns raw Numpy arrays (144 steps x 13 fuels).
    """
    def __init__(self):
        self.device = torch.device("cpu") # Cloud Run is CPU optimized
        self.regions = ['North', 'Central', 'South', 'East', 'Other']
        self.look_back = 720  # Input window size
        self.output_dim = 13  # Output fuels
        
        # 1. Resolve Paths
        # We assume the structure: /app/app/services/ml_inference.py -> /app/app/ml_artifacts
        self.base_path = Path(__file__).parent.parent / "ml_artifacts"
        
        logger.info(f"🔮 ML Service initializing. Artifacts path: {self.base_path}")
        
        # 2. Load Artifacts (Fail Fast if missing)
        self.scalers = self._load_scalers()
        self.models = self._load_models()

    def _load_scalers(self) -> Dict:
        path = self.base_path / "scalers.pkl"
        if not path.exists():
            # Critical failure: The app cannot function without this.
            raise FileNotFoundError(f"CRITICAL: scalers.pkl missing at {path}")
        return joblib.load(path)

    def _load_models(self) -> Dict[str, PureEncoderWithAttention]:
        models = {}
        params = {'d_model': 512, 'n_heads': 8, 'num_layers': 5, 'dropout': 0.2}

        print("\n\n🏁 DRIVING SCHOOL: STARTING MODEL LOAD 🏁\n") # Use print!

        for region in self.regions:
            path = self.base_path / f"Huber_model_{region.lower()}.pth"
            
            print(f"👉 Checking {region} at {path}...")
            
            if not path.exists():
                print(f"⚠️ Missing file: {path}")
                models[region] = None
                continue

            # --- CRITICAL CHECK: FILE SIZE ---
            file_size_kb = path.stat().st_size / 1024
            print(f"   📂 File Size: {file_size_kb:.2f} KB")
            
            if file_size_kb < 10:
                print("   🚨 CRITICAL: File is too small! This is likely a Git LFS pointer, not a model.")
                print("   👉 You need to pull the actual LFS files: 'git lfs pull'")
                models[region] = None
                continue
            # ---------------------------------

            try:
                print(f"   ⚖️ Loading State Dict for {region}...")
                
                # The stuck point
                state_dict = torch.load(path, map_location=self.device)
                print("   ✅ State Dict Loaded. Applying to model...")
                
                # Re-init model (simplified for brevity of probe)
                feature_list = self.scalers.get(region, {}).get('feature_cols', [])
                if not feature_list: feature_list = self.scalers.get(region.lower(), {}).get('feature_cols', [])
                
                model = PureEncoderWithAttention(len(feature_list), n_targets=self.output_dim, look_ahead=144, **params)
                model.load_state_dict(state_dict)
                model.eval()
                
                models[region] = model
                print(f"   🎉 {region} READY.")
                
            except Exception as e:
                print(f"   ❌ ERROR loading {region}: {e}")
                models[region] = None
        
        print("\n🏁 DRIVING SCHOOL: FINISHED 🏁\n")
        return models

    def predict(self, cache_data: Dict[str, List[RegionDataRow]]) -> Dict[str, np.ndarray]:
        """
        The Public API.
        Input: 
            cache_data: The full state (720+ rows) per region from Intelligence Service.
        Output: 
            Dict { "North": np.array([144, 13]), ... }
        """
        results = {}
        
        for region in self.regions:
            if not self.models.get(region):
                continue

            # 1. Extract Data for Region
            rows = cache_data.get(region, [])
            if not rows:
                continue

            # 2. Pydantic -> Pandas
            # Using model_dump() is cleaner and faster than manual dict creation
            data_dicts = [r.model_dump(by_alias=True) for r in rows]
            df = pd.DataFrame(data_dicts)

            # 3. Preprocess (Align columns, Scale, Tensorify)
            input_tensor = self._preprocess(df, region)
            
            if input_tensor is None:
                continue

            # 4. Inference
            with torch.no_grad():
                # Forward pass
                output = self.models[region](input_tensor)
                
                # Post-process:
                # a. Remove batch dimension (1, 144, 13) -> (144, 13)
                # b. Convert to Numpy
                # c. Clamp negative values (Physical generation cannot be negative)
                pred_np = output.squeeze(0).numpy()
                pred_np = np.maximum(pred_np, 0)
                
                results[region] = pred_np
                
        return results

    def _preprocess(self, df: pd.DataFrame, region: str) -> Optional[torch.Tensor]:
        # 1. Length Check
        if len(df) < self.look_back:
            logger.warning(f"Skipping {region}: Insufficient history ({len(df)}/{self.look_back})")
            return None

        # 2. Column Alignment (The "Contract" Check)
        # We trust the scaler to tell us which features the model needs.
        scaler_data = self.scalers.get(region) or self.scalers.get(region.lower())
        required_cols = scaler_data.get('feature_cols')
        
        # Verify all required columns exist in the input DF
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            logger.error(f"Schema Mismatch {region}: Missing {missing_cols[:3]}...")
            return None
            
        # 3. Slice and Sort
        # We take the *exact* columns needed, in the *exact* order needed.
        # This solves the "Extra Columns" issue: if Intelligence sends extra fields, they are dropped here.
        df_clean = df[required_cols].tail(self.look_back)
        
        # 4. Vectorized Scaling
        # (Value - Mean) / Std
        values = df_clean.values
        means = scaler_data['mean']
        stds = scaler_data['std']
        
        # Handle division by zero (if std is 0, usually implies constant value)
        # We add a tiny epsilon or just accept that 0/tiny is huge. 
        # Ideally, scalers are robust, but a safe production check is good.
        # For now, we trust the offline scaler.
        scaled_values = (values - means) / stds
        
        # 5. To Tensor
        return torch.from_numpy(scaled_values).float().unsqueeze(0).to(self.device)