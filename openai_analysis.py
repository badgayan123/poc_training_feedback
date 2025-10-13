"""
OpenAI Analysis Module for Training Feedback
This module provides AI-powered analysis of qualitative feedback using OpenAI GPT-4.
"""

import os
import openai
import logging
import json
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OpenAIFeedbackAnalyzer:
    """
    A class for analyzing qualitative feedback using OpenAI GPT-4.
    """
    
    def __init__(self):
        """Initialize the OpenAI client with API key from .env."""
        self.client = None
        self.model = "gpt-4"
        self._initialize_client()
    
    def _initialize_client(self):
        """Lazy initialize the OpenAI client using API key from .env"""
        try:
            if self.client is None:
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("OPENAI_API_KEY not found in environment variables")
                self.client = openai
                openai.api_key = api_key
        except Exception as e:
            logger.error(f"Error initializing OpenAI client: {e}")
            self.client = None
        
    def analyze_text_feedback(self, text: str) -> Dict[str, any]:
        if self.client is None:
            self._initialize_client()
            
        if self.client is None:
            return {
                "summary": "AI analysis temporarily unavailable. Please try again later.",
                "sentiment": "neutral",
                "suggestions": ["Please try again later when AI service is available"],
                "confidence": 0.0,
                "keywords": ["unavailable", "retry"]
            }
            
        if not text or not isinstance(text, str):
            raise ValueError("Text input must be a non-empty string")
        
        text = text.strip()
        if len(text) < 10:
            raise ValueError("Text must be at least 10 characters long")
        
        try:
            prompt = self._create_analysis_prompt(text)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert training feedback analyst. Analyze the provided feedback text and extract key insights, sentiment, and actionable suggestions. Always respond with valid JSON format."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=1000,
                timeout=30
            )
            
            analysis_result = self._parse_openai_response(response.choices[0].message.content)
            analysis_result['confidence'] = self._calculate_confidence(text, analysis_result)
            analysis_result['text_length'] = len(text)
            analysis_result['analysis_timestamp'] = self._get_timestamp()
            
            logger.info(f"Successfully analyzed feedback text (length: {len(text)} chars)")
            return analysis_result
            
        except openai.APIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise Exception(f"OpenAI API error: {str(e)}")
        except Exception as e:
            logger.error(f"Error analyzing feedback: {e}")
            raise Exception(f"Analysis failed: {str(e)}")
    
    def _create_analysis_prompt(self, text: str) -> str:
        prompt = f"""
Analyze the following training feedback text and provide a structured analysis:

FEEDBACK TEXT:
"{text}"

Please analyze this feedback and respond with a JSON object containing exactly these fields:

1. "summary": A concise 2-3 sentence summary capturing what the respondent is saying.
2. "sentiment": Classify the overall tone as one of: "positive", "neutral", or "negative".
3. "suggestions": Extract actionable improvement points mentioned. Return as an array of strings.
4. "keywords": Extract 3-5 key themes, topics, or concepts mentioned. Return as an array of strings.
5. "strengths": Identify what the respondent liked or found valuable. Return as an array of strings.
6. "concerns": Identify any issues, problems, or areas of dissatisfaction mentioned. Return as an array of strings.

Focus on actionable insights, balanced analysis of positives and negatives, and clear concise language.

Respond with valid JSON only, no additional text.
"""
        return prompt
    
    def _parse_openai_response(self, response_content: str) -> Dict[str, any]:
        try:
            response_content = response_content.strip()
            
            if response_content.startswith('```json'):
                response_content = response_content[7:]
            if response_content.endswith('```'):
                response_content = response_content[:-3]
            
            analysis = json.loads(response_content)
            
            required_fields = ['summary', 'sentiment', 'suggestions', 'keywords', 'strengths', 'concerns']
            for field in required_fields:
                if field not in analysis:
                    analysis[field] = [] if field in ['suggestions', 'keywords', 'strengths', 'concerns'] else ""
            
            valid_sentiments = ['positive', 'neutral', 'negative']
            if analysis['sentiment'] not in valid_sentiments:
                analysis['sentiment'] = 'neutral'
            
            for field in ['suggestions', 'keywords', 'strengths', 'concerns']:
                if not isinstance(analysis[field], list):
                    analysis[field] = []
            
            return analysis
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response as JSON: {e}")
            return self._create_fallback_analysis(response_content)
        except Exception as e:
            logger.error(f"Error parsing OpenAI response: {e}")
            return self._create_fallback_analysis(response_content)
    
    def _create_fallback_analysis(self, response_content: str) -> Dict[str, any]:
        return {
            "summary": "Analysis completed but response parsing failed. Raw response available for manual review.",
            "sentiment": "neutral",
            "suggestions": [],
            "keywords": [],
            "strengths": [],
            "concerns": [],
            "raw_response": response_content[:500] + "..." if len(response_content) > 500 else response_content,
            "parsing_error": True
        }
    
    def _calculate_confidence(self, text: str, analysis: Dict[str, any]) -> float:
        confidence = 0.5
        if len(text) > 100:
            confidence += 0.2
        if len(text) > 300:
            confidence += 0.1
        if analysis.get('summary') and len(analysis['summary']) > 20:
            confidence += 0.1
        if analysis.get('suggestions') and len(analysis['suggestions']) > 0:
            confidence += 0.1
        if analysis.get('keywords') and len(analysis['keywords']) > 0:
            confidence += 0.1
        return min(confidence, 1.0)
    
    def _get_timestamp(self) -> str:
        from datetime import datetime
        return datetime.utcnow().isoformat()
    
    def analyze_multiple_feedbacks(self, feedback_texts: List[str]) -> List[Dict[str, any]]:
        results = []
        for i, text in enumerate(feedback_texts):
            try:
                analysis = self.analyze_text_feedback(text)
                analysis['feedback_index'] = i
                results.append(analysis)
            except Exception as e:
                logger.error(f"Error analyzing feedback {i}: {e}")
                results.append({
                    "error": str(e),
                    "feedback_index": i,
                    "summary": "Analysis failed",
                    "sentiment": "neutral",
                    "suggestions": [],
                    "keywords": [],
                    "strengths": [],
                    "concerns": []
                })
        return results

# Global analyzer instance - lazy loaded
analyzer = None

def get_analyzer():
    global analyzer
    if analyzer is None:
        analyzer = OpenAIFeedbackAnalyzer()
    return analyzer

def analyze_text_feedback(text: str) -> Dict[str, any]:
    analyzer_instance = get_analyzer()
    return analyzer_instance.analyze_text_feedback(text)

def analyze_multiple_feedbacks(feedback_texts: List[str]) -> List[Dict[str, any]]:
    analyzer_instance = get_analyzer()
    return analyzer_instance.analyze_multiple_feedbacks(feedback_texts)

# -----------------------------------------
# Comprehensive feedback analysis functions
# -----------------------------------------

def analyze_comprehensive_training_feedback(training_id: str, all_feedbacks: list) -> dict:
    try:
        analyzer_instance = get_analyzer()
        if analyzer_instance.client is None:
            analyzer_instance._initialize_client()
            
        quantitative_data = []
        qualitative_texts = []
        
        for feedback in all_feedbacks:
            if 'quantitative' in feedback:
                quantitative_data.append(feedback['quantitative'])
            if 'qualitative' in feedback:
                qual_text = ""
                for key, value in feedback['qualitative'].items():
                    if value and isinstance(value, str) and value.strip():
                        qual_text += f"{key.replace('_', ' ').title()}: {value.strip()}\n"
                if qual_text.strip():
                    qualitative_texts.append(qual_text.strip())
        
        quantitative_insights = {}
        if quantitative_data:
            metrics = list(quantitative_data[0].keys())
            for metric in metrics:
                values = [q.get(metric) for q in quantitative_data if q.get(metric) is not None]
                if values:
                    quantitative_insights[metric] = {
                        'average': round(sum(values) / len(values), 2),
                        'min': min(values),
                        'max': max(values),
                        'count': len(values),
                        'distribution': {
                            'excellent_5': len([v for v in values if v == 5]),
                            'very_good_4': len([v for v in values if v == 4]),
                            'good_3': len([v for v in values if v == 3]),
                            'fair_2': len([v for v in values if v == 2]),
                            'poor_1': len([v for v in values if v == 1])
                        }
                    }
        
        combined_qualitative = f"Training ID: {training_id}\nTotal Feedback Records: {len(all_feedbacks)}\n\n"
        combined_qualitative += "QUALITATIVE FEEDBACK FROM ALL PARTICIPANTS:\n\n"
        for i, qual_text in enumerate(qualitative_texts, 1):
            combined_qualitative += f"--- Participant {i} ---\n{qual_text}\n\n"
        
        try:
            qualitative_analysis = analyzer_instance.analyze_text_feedback(combined_qualitative)
        except Exception as e:
            logger.error(f"Error in qualitative analysis: {e}")
            qualitative_analysis = {
                "summary": f"Analysis of {len(qualitative_texts)} qualitative feedback responses for training {training_id} completed using fallback method.",
                "sentiment": "neutral",
                "suggestions": ["Review individual feedback for detailed insights"],
                "keywords": ["training", "feedback", "evaluation", "analysis"],
                "strengths": ["Multiple participants provided feedback"],
                "concerns": ["API quota exceeded - using fallback analysis"],
                "confidence": 0.6
            }
        
        polarization_score = _compute_polarization(all_feedbacks)
        enhanced_analysis = _generate_enhanced_analysis(training_id, quantitative_insights, qualitative_analysis, len(all_feedbacks), polarization_score)
        
        return {
            "training_id": training_id,
            "total_participants": len(all_feedbacks),
            "qualitative_analysis": qualitative_analysis,
            "quantitative_insights": quantitative_insights,
            "enhanced_analysis": enhanced_analysis,
            "polarization": {
                "score": polarization_score,
                "level": "high" if polarization_score >= 75 else ("medium" if polarization_score >= 50 else "low")
            },
            "data_summary": {
                "quantitative_responses": len(quantitative_data),
                "qualitative_responses": len(qualitative_texts),
                "overall_average_rating": round(sum([sum(q.values()) / len(q) for q in quantitative_data]) / len(quantitative_data), 2) if quantitative_data else 0
            },
            "summary": enhanced_analysis.get("executive_summary", "No summary available"),
            "sentiment": enhanced_analysis.get("overall_sentiment", "neutral"),
            "suggestions": enhanced_analysis.get("recommendations", ["No suggestions available"]),
            "risk_assessment": enhanced_analysis.get("risk_level", "medium"),
            "quantitative_analysis": quantitative_insights,
            "all_feedbacks": all_feedbacks
        }
        
    except Exception as e:
        logger.error(f"Error in analyze_comprehensive_training_feedback: {e}")
        raise Exception(f"Comprehensive analysis failed: {str(e)}")

# -----------------------------------------
# Helper functions
# -----------------------------------------

def _generate_enhanced_analysis(training_id, quantitative_insights, qualitative_analysis, total_feedbacks, polarization_score=0):
    """
    Generates enhanced analysis including polarization detection
    """
    overall_avg = 0
    poor_percentage = 0
    excellent_percentage = 0
    total_participants = total_feedbacks

    if quantitative_insights:
        total_scores = []
        for metric, stats in quantitative_insights.items():
            total_scores.extend([metric_val for metric_val in range(stats['min'], stats['max']+1)])
        if total_scores:
            overall_avg = sum(total_scores)/len(total_scores)
        for metric, stats in quantitative_insights.items():
            total = stats['count']
            poor_percentage += stats['distribution'].get('poor_1', 0)/total*100
            excellent_percentage += stats['distribution'].get('excellent_5', 0)/total*100

    polarization_detected = False
    if poor_percentage > 20 and excellent_percentage > 20:
        polarization_detected = True

    polarization_solutions = _create_enhanced_polarization_solutions(
        polarization_detected, quantitative_insights, overall_avg, poor_percentage, excellent_percentage, total_participants
    )

    return {
        "executive_summary": f"Processed {total_feedbacks} feedbacks for training {training_id}.",
        "overall_sentiment": qualitative_analysis.get("sentiment", "neutral"),
        "consensus_analysis": "Analysis complete",
        "key_strengths": qualitative_analysis.get("strengths", []),
        "critical_improvements": qualitative_analysis.get("concerns", []),
        "quantitative_insights": quantitative_insights,
        "polarization_detected": polarization_detected or polarization_score >= 50,
        "polarization_score": round(polarization_score, 1),
        "polarization_solutions": polarization_solutions,
        "recommendations": qualitative_analysis.get("suggestions", []),
        "risk_level": "medium",
        "priority_areas": ["Content quality", "Trainer effectiveness"],
        "success_indicators": ["Positive feedback trends"],
        "confidence": qualitative_analysis.get("confidence", 0.7)
    }

def _create_enhanced_polarization_solutions(polarization_detected, quantitative_insights, overall_avg, poor_percentage, excellent_percentage, total_participants):
    if not polarization_detected:
        return {}

    solutions = {
        "communication": "Discuss the feedback split with the training team to understand reasons for divergent responses.",
        "content_adjustment": "Adjust training content to better address both groups' needs.",
        "follow_up": "Conduct follow-up sessions or surveys to clarify concerns.",
        "segmentation": "Segment participants by experience level to tailor future sessions.",
        "monitoring": "Track changes in feedback over subsequent sessions."
    }

    return solutions


def _compute_polarization(all_feedbacks: list) -> float:
    """
    Compute a polarization percentage based on contradictory responses.
    Heuristics:
    - From quantitative: count pairs of metrics that are semantically close
      (e.g., communication_skills vs clarity_explanation/understanding proxies) with opposite extremes.
    - From qualitative: if the same feedback contains conflicting sentiment keywords (good vs bad) adjacent categories, count contradiction.
    - Return percentage of feedbacks that have at least one contradiction, scaled to 0-100.
    """
    if not all_feedbacks:
        return 0.0

    # Metric pairs to compare for contradiction (expandable)
    metric_pairs = [
        ("communication_skills", "clarity_explanation"),
        ("communication_skills", "overall_satisfaction"),
        ("clarity_explanation", "overall_satisfaction"),
    ]

    positive_words = {"good", "great", "excellent", "amazing", "clear", "understandable"}
    negative_words = {"bad", "terrible", "confusing", "unclear", "boring", "difficult", "hard", "poor"}

    contradictory_count = 0

    for fb in all_feedbacks:
        has_contradiction = False

        # Quantitative contradictions: one metric very high (>=5) and paired metric very low (<=1)
        q = fb.get("quantitative") or {}
        for a, b in metric_pairs:
            va = q.get(a)
            vb = q.get(b)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                if (va >= 5 and vb <= 1) or (vb >= 5 and va <= 1):
                    has_contradiction = True
                    break

        # Qualitative contradictions: contains both a positive and a negative keyword
        if not has_contradiction:
            qual = fb.get("qualitative") or {}
            text = " ".join([str(v) for v in qual.values() if isinstance(v, str)])
            lower = text.lower()
            if lower:
                contains_pos = any(w in lower for w in positive_words)
                contains_neg = any(w in lower for w in negative_words)
                if contains_pos and contains_neg:
                    has_contradiction = True

        # Dynamic structured answers, if present
        if not has_contradiction:
            dyn = fb.get("dynamic_answers") or []
            # If any pair of answers within the same feedback shows extremes and neutralizing text
            choice_vals = [d.get("value") for d in dyn if d.get("type") == "choice" and isinstance(d.get("value"), (int, float))]
            if any(v >= 5 for v in choice_vals) and any(v <= 1 for v in choice_vals):
                has_contradiction = True
            else:
                texts = " ".join([str(d.get("value")) for d in dyn if d.get("type") == "subjective" and isinstance(d.get("value"), str)])
                lower2 = texts.lower()
                if lower2:
                    if any(w in lower2 for w in positive_words) and any(w in lower2 for w in negative_words):
                        has_contradiction = True

        if has_contradiction:
            contradictory_count += 1

    return round((contradictory_count / len(all_feedbacks)) * 100.0, 1)

# -----------------------------
# Example usage
# -----------------------------
if __name__ == "__main__":
    test_feedback = "The training was good but could have been longer. Exercises were helpful."
    result = analyze_text_feedback(test_feedback)
    print(json.dumps(result, indent=2))
