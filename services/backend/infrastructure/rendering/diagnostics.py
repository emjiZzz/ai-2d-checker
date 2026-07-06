import time
from collections.abc import Callable
from typing import Any

from ...logger import logger


class RenderingDiagnostics:
    """
    Performance profiling tools for tracking DXF geometry serialization
    and rendering payload creation times.
    """
    
    @staticmethod
    def profile_serialization(func: Callable, *args, **kwargs) -> Any:
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        
        # Calculate entity count if result is standard payload
        entity_count = 0
        if isinstance(result, dict) and "layers" in result:
            entity_count = sum(len(layer) for layer in result["layers"].values())
            
        logger.info(f"Serialization profile: processed {entity_count} entities in {duration:.4f}s")
        return result
