# scripts/deployment.py

"""
Deployment Module

This module handles the deployment of the trained machine learning model as a RESTful API
using FastAPI. It includes endpoints for making predictions and health checks.
"""

import os
import logging
from turtle import pd
import joblib
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict
from starlette.middleware.cors import CORSMiddleware
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
import uvicorn

# Configure Logging
logging.basicConfig(
    filename='logs/deployment.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Marvin Agent System - Prediction API",
    description="API for making predictions using the trained Random Forest model.",
    version="1.0.0"
)

# Enable CORS for all origins (adjust in production as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PredictionRequest(BaseModel):
    """
    Schema for prediction requests.
    """
    features: Dict[str, Any]

class PredictionResponse(BaseModel):
    """
    Schema for prediction responses.
    """
    prediction: Any
    probabilities: Dict[str, float]

def load_model(model_path: str) -> Pipeline:
    """
    Loads the trained machine learning model pipeline.

    Args:
        model_path (str): Path to the saved model.

    Returns:
        Pipeline: The trained model pipeline.

    Raises:
        FileNotFoundError: If the model file does not exist.
        Exception: If the model fails to load.
    """
    if not os.path.exists(model_path):
        logger.error(f"Model file not found at {model_path}")
        raise FileNotFoundError(f"Model file not found at {model_path}")
    try:
        model = joblib.load(model_path)
        if not isinstance(model, Pipeline):
            logger.error("Loaded model is not a Pipeline instance")
            raise TypeError("Loaded model is not a Pipeline instance")
        logger.info(f"Loaded model pipeline from {model_path}")
        return model
    except Exception as e:
        logger.exception(f"Failed to load model: {e}")
        raise

# Load the model at startup
MODEL_PATH = 'models/random_forest.joblib'
model_pipeline: Pipeline = load_model(MODEL_PATH)

@app.get("/health", tags=["Health"])
def health_check():
    """
    Health check endpoint to verify that the API is running.
    """
    logger.info("Health check requested")
    return {"status": "healthy"}

@app.post("/predict", response_model=PredictionResponse, tags=["Prediction"])
def predict(request: PredictionRequest):
    """
    Endpoint to make predictions using the trained model.

    Args:
        request (PredictionRequest): The input features for prediction.

    Returns:
        PredictionResponse: The prediction result and probabilities.

    Raises:
        HTTPException: If prediction fails.
    """
    try:
        logger.info(f"Received prediction request: {request.features}")
        input_data = pd.DataFrame([request.features])
        prediction = model_pipeline.predict(input_data)[0]
        probabilities = model_pipeline.predict_proba(input_data)[0].tolist()
        class_probabilities = {
            str(cls): prob for cls, prob in zip(model_pipeline.named_steps['preprocessor'].transformers_[1][1].named_steps['onehot'].categories_[0], probabilities)
        }
        logger.info(f"Prediction: {prediction}, Probabilities: {class_probabilities}")
        return PredictionResponse(prediction=prediction, probabilities=class_probabilities)
    except Exception as e:
        logger.exception(f"Prediction failed: {e}")
        raise HTTPException(status_code=500, detail="Prediction failed")

def run_api():
    """
    Runs the FastAPI application using Uvicorn.
    """
    uvicorn.run(
        "deployment:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=4
    )

if __name__ == "__main__":
    run_api()
