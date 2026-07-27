"""
Qualification ML Model
Scikit-learn based classification model for lead qualification
"""

from typing import Dict, Any, Optional, List, Tuple
import logging
import os
import pickle
import numpy as np
from datetime import datetime

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

logger = logging.getLogger(__name__)


class QualificationModel:
    """
    Machine learning model for lead qualification
    Uses sklearn RandomForestClassifier with feature engineering
    """
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        threshold: float = 0.5,
    ):
        """
        Initialize qualification model
        
        Args:
            model_path: Path to saved model file
            threshold: Classification threshold (0-1)
        """
        self.model_path = model_path or os.path.join(os.getenv('MODEL_PATH', './models/'), 'qualification_model.pkl')
        self.scaler_path = os.path.join(os.path.dirname(self.model_path), 'qualification_scaler.pkl')
        self.threshold = threshold
        self.model: Optional[RandomForestClassifier] = None
        self.scaler: Optional[StandardScaler] = None
        self.is_trained = False
        self.feature_names = [
            'company_size',
            'engagement_score',
            'response_time_hours',
            'page_views',
            'email_opens',
            'link_clicks',
            'has_budget',
            'is_decision_maker',
            'target_industry',
            'verified_contact',
        ]
        
        # Try to load pre-trained model
        if os.path.exists(self.model_path):
            self._load_model()
    
    def _load_model(self) -> bool:
        """Load pre-trained model from disk"""
        try:
            with open(self.model_path, 'rb') as f:
                self.model = pickle.load(f)
            logger.info(f"Loaded model from {self.model_path}")
            
            if os.path.exists(self.scaler_path):
                with open(self.scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                logger.info(f"Loaded scaler from {self.scaler_path}")
            
            self.is_trained = True
            return True
        except Exception as e:
            logger.warning(f"Failed to load model: {str(e)}")
            return False
    
    def _extract_features(self, lead_data: Dict[str, Any]) -> np.ndarray:
        """
        Extract feature vector from lead data
        
        Args:
            lead_data: Lead data dictionary
            
        Returns:
            Feature vector array
        """
        features = []
        
        # Numeric features
        features.append(float(lead_data.get('company_size', 0)))
        features.append(float(lead_data.get('engagement_score', 0)))
        features.append(float(lead_data.get('response_time_hours', 999)))
        features.append(float(lead_data.get('page_views', 0)))
        features.append(float(lead_data.get('email_opens', 0)))
        features.append(float(lead_data.get('link_clicks', 0)))
        
        # Boolean features (convert to 0/1)
        features.append(1.0 if lead_data.get('has_budget') else 0.0)
        features.append(1.0 if lead_data.get('is_decision_maker') else 0.0)
        
        # Categorical features
        target_industries = ['Technology', 'Finance', 'Healthcare', 'SaaS', 'Enterprise']
        industry = lead_data.get('industry', '')
        features.append(1.0 if industry in target_industries else 0.0)
        
        # Contact quality features
        features.append(1.0 if lead_data.get('email_verified') else 0.0)
        
        return np.array(features, dtype=np.float32).reshape(1, -1)
    
    def predict(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Predict qualification for a lead
        
        Args:
            lead_data: Lead data to predict on
            
        Returns:
            Prediction result with score and label
        """
        if not SKLEARN_AVAILABLE:
            return {
                'qualified': False,
                'score': 0.0,
                'probability': 0.0,
                'method': 'error',
                'error': 'sklearn not available',
            }
        
        if not self.is_trained:
            return {
                'qualified': False,
                'score': 0.0,
                'probability': 0.0,
                'method': 'untrained',
                'message': 'Model not trained - using fallback logic',
            }
        
        try:
            # Extract features
            X = self._extract_features(lead_data)
            
            # Scale features if scaler available
            if self.scaler:
                X = self.scaler.transform(X)
            
            # Predict probability
            assert self.model is not None
            probability = self.model.predict_proba(X)[0][1]
            
            # Apply threshold
            qualified = probability >= self.threshold
            
            result = {
                'qualified': qualified,
                'score': float(probability),
                'probability': float(probability),
                'threshold': self.threshold,
                'method': 'sklearn_random_forest',
                'lead_id': lead_data.get('id', 'unknown'),
            }
            
            logger.debug(
                f"ML prediction: {probability:.2%} probability",
                extra={'lead_id': lead_data.get('id'), 'qualified': qualified},
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Prediction error: {str(e)}")
            return {
                'qualified': False,
                'score': 0.0,
                'probability': 0.0,
                'method': 'error',
                'error': str(e),
            }
    
    def train(self, X_train: np.ndarray, y_train: np.ndarray) -> bool:
        """
        Train the model on provided data
        
        Args:
            X_train: Training features array
            y_train: Training labels array
            
        Returns:
            True if training successful
        """
        if not SKLEARN_AVAILABLE:
            logger.error("sklearn not available for training")
            return False
        
        try:
            logger.info(f"Training Random Forest model on {len(X_train)} samples")
            
            # Scale features
            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X_train)
            
            # Train model
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1,
                class_weight='balanced',
            )
            self.model.fit(X_scaled, y_train)
            
            self.is_trained = True
            logger.info("Model training completed")
            
            # Save model and scaler
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            
            with open(self.model_path, 'wb') as f:
                pickle.dump(self.model, f)
            logger.info(f"Saved model to {self.model_path}")
            
            with open(self.scaler_path, 'wb') as f:
                pickle.dump(self.scaler, f)
            logger.info(f"Saved scaler to {self.scaler_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"Training error: {str(e)}")
            self.is_trained = False
            return False
    
    def get_feature_importance(self) -> Optional[Dict[str, float]]:
        """Get feature importance from trained model"""
        if not self.is_trained or self.model is None or not hasattr(self.model, 'feature_importances_'):
            return None

        importance_dict = {}
        for name, importance in zip(self.feature_names, self.model.feature_importances_):
            importance_dict[name] = float(importance)
        
        return dict(sorted(importance_dict.items(), key=lambda x: x[1], reverse=True))
