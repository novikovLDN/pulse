"""LLM service for structured extraction and report generation."""
from openai import OpenAI
from typing import Dict, Any, List
from config import settings
from loguru import logger
import json


class LLMService:
    """Service for LLM interactions."""
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.base_model = settings.openai_model
        self.premium_model = settings.openai_premium_model
    
    def extract_structured_data(self, raw_text: str) -> Dict[str, Any]:
        """Extract structured laboratory data from raw text."""
        prompt = """You are a medical data extraction system. Extract laboratory test results from the provided text and return ONLY valid JSON.

Extract:
- Analyte names (test names)
- Numeric values
- Units of measurement
- Reference ranges (normal ranges)
- Flags (low, high, normal, critical)

Return format:
{
  "analytes": [
    {
      "name": "Ferritin",
      "value": "30",
      "unit": "ng/mL",
      "reference_range": "20-250",
      "flag": "low"
    }
  ]
}

If a value is below the reference range, flag should be "low".
If a value is above the reference range, flag should be "high".
If a value is within the reference range, flag should be "normal".

Text to process:
{text}

Return ONLY the JSON object, no additional text."""

        try:
            response = self.client.chat.completions.create(
                model=self.base_model,
                messages=[
                    {"role": "system", "content": "You are a medical data extraction system. Return only valid JSON."},
                    {"role": "user", "content": prompt.format(text=raw_text)}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
        except Exception as e:
            logger.error(f"Error extracting structured data: {e}")
            raise
    
    def generate_clinical_report(
        self,
        structured_data: Dict[str, Any],
        clinical_context: Dict[str, Any],
        use_premium: bool = False
    ) -> str:
        """Generate clinical interpretation report."""
        
        model = self.premium_model if use_premium else self.base_model
        
        system_prompt = """You are a clinical laboratory interpretation assistant. Your role is to provide structured, evidence-based analysis of laboratory results.

CRITICAL RULES:
1. NEVER provide a diagnosis
2. NEVER prescribe treatment
3. Use academic, calm, evidence-based tone
4. Avoid definitive medical claims
5. Use phrases like "may indicate", "can be associated with", "requires further evaluation"
6. NEVER say "You have...", "This is a diagnosis", "You must take..."
7. Do not use emojis
8. Maintain a calm, non-alarmist tone

Report Structure:
1. Clinical Overview
2. Significant Deviations
3. Possible Causes (differential reasoning)
4. Recommended Additional Tests
5. When In-Person Consultation Is Advisable
6. Simplified Explanation"""

        user_prompt = f"""Analyze the following laboratory results and clinical context.

Laboratory Results:
{json.dumps(structured_data, indent=2, ensure_ascii=False)}

Clinical Context:
- Age: {clinical_context.get('age', 'Not provided')}
- Sex: {clinical_context.get('sex', 'Not provided')}
- Symptoms: {clinical_context.get('symptoms', 'Not provided')}
- Pregnancy: {clinical_context.get('pregnancy', 'Not applicable')}
- Chronic Conditions: {clinical_context.get('chronic_conditions', 'None')}
- Medications: {clinical_context.get('medications', 'None')}

Generate a structured clinical interpretation report following the specified format."""

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating clinical report: {e}")
            raise
    
    def compare_analyses(
        self,
        analysis1: Dict[str, Any],
        analysis2: Dict[str, Any],
        clinical_context1: Dict[str, Any],
        clinical_context2: Dict[str, Any]
    ) -> str:
        """Compare two analyses and generate dynamic report."""
        
        system_prompt = """You are a clinical laboratory interpretation assistant specializing in longitudinal analysis. Compare two sets of laboratory results and identify trends and changes.

CRITICAL RULES:
1. NEVER provide a diagnosis
2. Use academic, calm, evidence-based tone
3. Focus on dynamic changes and trends
4. Use phrases like "may indicate", "can be associated with"
5. Do not use emojis

Report Structure:
1. Dynamic Overview
2. Markers Increasing
3. Markers Decreasing
4. Clinical Significance
5. Suggested Follow-Up"""

        user_prompt = f"""Compare these two laboratory analyses:

Analysis 1 (Date: {clinical_context1.get('date', 'Unknown')}):
{json.dumps(analysis1, indent=2, ensure_ascii=False)}

Analysis 2 (Date: {clinical_context2.get('date', 'Unknown')}):
{json.dumps(analysis2, indent=2, ensure_ascii=False)}

Generate a comparison report focusing on changes and trends."""

        try:
            response = self.client.chat.completions.create(
                model=self.base_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error comparing analyses: {e}")
            raise
    
    def answer_follow_up_question(
        self,
        structured_data: Dict[str, Any],
        clinical_context: Dict[str, Any],
        original_report: str,
        question: str
    ) -> str:
        """Answer follow-up question about an analysis."""
        
        system_prompt = """You are a clinical laboratory interpretation assistant answering a follow-up question about a previous analysis.

CRITICAL RULES:
1. NEVER provide a diagnosis
2. NEVER prescribe treatment
3. Use academic, calm, evidence-based tone
4. Reference only the provided analysis
5. Use phrases like "may indicate", "can be associated with"
6. Do not use emojis
7. Keep answers concise and focused"""

        user_prompt = f"""Original Analysis Report:
{original_report}

Laboratory Results:
{json.dumps(structured_data, indent=2, ensure_ascii=False)}

Clinical Context:
{json.dumps(clinical_context, indent=2, ensure_ascii=False)}

Follow-up Question: {question}

Provide a clear, evidence-based answer to this question."""

        try:
            response = self.client.chat.completions.create(
                model=self.base_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error answering follow-up question: {e}")
            raise
