"""
Generation request/response models
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from enum import Enum


class StatisticalWeightPreference(str, Enum):
    """Statistical weighting preferences"""
    FREQUENCY = "frequency"
    BALANCED = "balanced"
    RANDOM = "random"


class GameConstraints(BaseModel):
    """Game generation constraints"""
    numbers_per_game: int = Field(6, ge=6, le=15, description="Numbers per game (6-15)")
    min_repetition: Optional[int] = Field(None, ge=0, description="Minimum repetition across games")
    max_repetition: Optional[int] = Field(None, ge=0, description="Maximum repetition across games")
    min_odd: Optional[int] = Field(None, ge=0, le=15, description="Minimum odd numbers per game")
    max_odd: Optional[int] = Field(None, ge=0, le=15, description="Maximum odd numbers per game")
    min_even: Optional[int] = Field(None, ge=0, le=15, description="Minimum even numbers per game")
    max_even: Optional[int] = Field(None, ge=0, le=15, description="Maximum even numbers per game")
    fixed_numbers: Optional[List[int]] = Field(None, description="Numbers that must appear in all games")
    seed: Optional[int] = Field(None, description="Random seed for reproducibility")
    
    @field_validator('fixed_numbers')
    @classmethod
    def validate_fixed_numbers(cls, v):
        if v is not None:
            # Remove the limit of 15 - users can provide as many fixed numbers as they want
            # The system will use ONLY these numbers to generate games
            if any(n < 1 or n > 60 for n in v):
                raise ValueError("Fixed numbers must be between 1 and 60")
            if len(set(v)) != len(v):
                raise ValueError("Fixed numbers must be unique")
        return v
    
    @field_validator('min_odd', 'max_odd', 'min_even', 'max_even')
    @classmethod
    def validate_odd_even_constraints(cls, v, info):
        if v is not None and info.data.get('numbers_per_game'):
            if v > info.data['numbers_per_game']:
                raise ValueError(f"{info.field_name} cannot exceed numbers_per_game")
        return v


class GenerationMode(str, Enum):
    """Generation mode"""
    BY_BUDGET = "by_budget"  # User specifies budget, quantity is calculated
    BY_QUANTITY = "by_quantity"  # User specifies quantity, budget is calculated


class GenerationRequest(BaseModel):
    """Generation request model"""
    mode: GenerationMode = Field(..., description="Generation mode: by_budget or by_quantity")
    budget: Optional[float] = Field(None, gt=0, description="Budget in BRL (required if mode is by_budget)")
    quantity: Optional[int] = Field(None, gt=0, le=1000, description="Number of games to generate (required if mode is by_quantity)")
    constraints: GameConstraints = Field(..., description="Game generation constraints")
    
    @field_validator('budget')
    @classmethod
    def validate_budget(cls, v, info):
        mode = info.data.get('mode')
        if mode == GenerationMode.BY_BUDGET:
            if v is None or v <= 0:
                raise ValueError("Budget is required when mode is 'by_budget'")
        return v
    
    @field_validator('quantity')
    @classmethod
    def validate_quantity(cls, v, info):
        mode = info.data.get('mode')
        if mode == GenerationMode.BY_QUANTITY:
            if v is None or v <= 0:
                raise ValueError("Quantity is required when mode is 'by_quantity'")
        return v
    
    @model_validator(mode='after')
    def validate_mode_requirements(self):
        """Validate mode-specific requirements after initialization"""
        if self.mode == GenerationMode.BY_BUDGET and (not self.budget or self.budget <= 0):
            raise ValueError("Budget is required when mode is 'by_budget'")
        if self.mode == GenerationMode.BY_QUANTITY and (not self.quantity or self.quantity <= 0):
            raise ValueError("Quantity is required when mode is 'by_quantity'")
        return self


class GenerationResponse(BaseModel):
    """Generation response model"""
    process_id: str = Field(..., description="Process ID for tracking")
    status: str = Field(..., description="Job status")
    message: str = Field(..., description="Status message")

