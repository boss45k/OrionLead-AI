"""
Model Loader and Manager
- Loads all ML models at application startup
- Provides thread-safe access to cached models
- Reduces disk I/O and improves performance significantly
"""

import pickle
import threading
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


logger = logging.getLogger(__name__)


class ModelManager:
    """Singleton for managing ML model lifecycle"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize model manager and load all models"""
        self.models: Dict[str, Any] = {}
        self.model_metadata: Dict[str, dict] = {}
        self._load_all_models()
    
    def _load_all_models(self):
        """Load all ML models from disk into memory at startup"""
        model_path = Path('models')
        
        if not model_path.exists():
            logger.warning(f"Models directory not found at {model_path}")
            return
        
        # Load Qualification Model
        qual_path = model_path / 'qualification_model.pkl'
        if qual_path.exists():
            try:
                with open(qual_path, 'rb') as f:
                    self.models['qualification'] = pickle.load(f)
                    self.model_metadata['qualification'] = {
                        'version': '1.0',
                        'loaded_at': datetime.utcnow().isoformat(),
                        'path': str(qual_path),
                        'type': 'RandomForestClassifier',
                        'features': 10
                    }
                logger.info(f"✓ Loaded qualification model from {qual_path}")
            except Exception as e:
                logger.error(f"Failed to load qualification model: {e}")
        else:
            logger.debug(f"Qualification model not found at {qual_path} (optional)")
        
        # Add more models here as needed
        # For example:
        # intent_path = model_path / 'intent_model.pkl'
        # if intent_path.exists():
        #     with open(intent_path, 'rb') as f:
        #         self.models['intent'] = pickle.load(f)
        
        logger.info(f"✓ Model manager initialized with {len(self.models)} models in memory")
    
    def get_model(self, model_name: str) -> Any:
        """
        Get a cached model by name
        
        Args:
            model_name: Name of the model (e.g., 'qualification')
        
        Returns:
            The loaded model object
        
        Raises:
            ValueError: If model is not loaded
        """
        if model_name not in self.models:
            raise ValueError(
                f"Model '{model_name}' not loaded. Available: {list(self.models.keys())}"
            )
        return self.models[model_name]
    
    def get_metadata(self, model_name: str) -> Dict[str, Any]:
        """
        Get metadata about a loaded model
        
        Args:
            model_name: Name of the model
        
        Returns:
            Dictionary with model metadata (version, load time, etc.)
        """
        return self.model_metadata.get(model_name, {})
    
    def get_all_models(self) -> Dict[str, Any]:
        """Get all loaded models"""
        return self.models.copy()
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get health status of model system
        
        Returns:
            Status dictionary with model counts and metadata
        """
        return {
            'status': 'ok' if self.models else 'no_models_loaded',
            'models_loaded': len(self.models),
            'models': list(self.models.keys()),
            'metadata': self.model_metadata
        }


def initialize_models():
    """Initialize the model manager (call during app startup)"""
    manager = ModelManager()
    logger.info(f"Models initialized: {manager.get_health_status()}")
    return manager
