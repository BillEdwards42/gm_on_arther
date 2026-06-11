# Machine Learning Inference Engine

The ML Inference Engine (`app.services.ml_inference`) is responsible for executing the pre-trained PyTorch models to predict future power generation.

## 1. Model Architecture
The core model is an exact replica of the training architecture: `PureEncoderWithAttention`.
- **Encoder Layer:** Uses a multi-layer Long Short-Term Memory (LSTM) network to process sequential data.
- **Attention Mechanism:** Implements Multihead Attention to focus on critical time steps within the look-back window.
- **Feed Forward Network:** Maps the attention output to the final prediction space.
- **Look-back (Input):** 720 time steps (5 days, 10-minute intervals).
- **Look-ahead (Output):** 144 time steps (24 hours).
- **Targets:** 13 distinct fuel types per region.

## 2. Artifact Loading
When the service initializes, it attempts to load local ML artifacts from the `/app/ml_artifacts` directory.
- **Scalers (`scalers.pkl`):** Required to normalize the raw input data (Value - Mean / Std) to the scale the model expects.
- **Models (`Huber_model_{region}.pth`):** PyTorch state dictionaries containing the trained weights for each specific region.
- *Note:* The code includes a critical check to ensure the `.pth` files are actual models and not Git LFS pointers (file size > 10KB).

## 3. Inference Workflow
1. **Pydantic to Pandas:** The engine receives clean Pydantic objects from the intelligence pipeline and converts them into a Pandas DataFrame.
2. **Column Alignment:** It dynamically selects the required columns based on the contract defined in `scalers.pkl`. This ensures any extra features injected by the intelligence pipeline are safely dropped.
3. **Scaling:** Applies the mean and standard deviation from the scaler to normalize the 720-step input window.
4. **Tensorization:** Converts the normalized numpy array into a PyTorch tensor and moves it to the CPU (Cloud Run relies on CPU execution).
5. **Prediction & Post-processing:** 
   - Runs the forward pass of the model.
   - Squeezes the batch dimension.
   - Converts back to a Numpy array.
   - Applies a `np.maximum(pred_np, 0)` clamp, as physical power generation cannot be negative.

## 4. Hardware Considerations
The service is explicitly configured to use `torch.device("cpu")`. Google Cloud Run does not natively support GPUs in standard environments, so the architecture is optimized for fast CPU inference.
