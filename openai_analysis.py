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
        
        # Calculate polarization check
        polarization_analysis = _compute_polarization_analysis(all_feedbacks)
        
        enhanced_analysis = _generate_enhanced_analysis(training_id, quantitative_insights, qualitative_analysis, len(all_feedbacks), polarization_analysis)
        
        return {
            "training_id": training_id,
            "total_participants": len(all_feedbacks),
            "qualitative_analysis": qualitative_analysis,
            "quantitative_insights": quantitative_insights,
            "polarization_check": polarization_analysis,
            "enhanced_analysis": enhanced_analysis,
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

def _compute_polarization_analysis(all_feedbacks: list) -> dict:
    """
    Compute polarization analysis based on contradictory responses in quantitative feedback.
    
    Polarization occurs when participants give extreme opposing ratings for related questions.
    For example: 5/5 for communication skills but 1/5 for understanding the trainer.
    
    Returns:
        dict: Polarization analysis with score, level, and detailed breakdown
    """
    try:
        if not all_feedbacks:
            return {
                "polarization_score": 0.0,
                "polarization_level": "low",
                "contradictory_responses": 0,
                "total_responses": 0,
                "analysis": "No feedback data available for polarization analysis"
            }
        
        contradictory_responses = 0
        total_responses = 0
        polarization_details = []
        
        # Define related question pairs for polarization detection
        related_question_pairs = [
            ("content_quality", "clarity_of_explanation"),
            ("trainer_effectiveness", "clarity_of_explanation"),
            ("trainer_effectiveness", "engagement_interaction"),
            ("content_quality", "practical_relevance"),
            ("clarity_of_explanation", "practical_relevance")
        ]
        
        for feedback in all_feedbacks:
            if 'quantitative' not in feedback:
                continue
                
            quantitative = feedback['quantitative']
            total_responses += 1
            
            # Check for contradictory responses within this participant's feedback
            is_contradictory = False
            contradiction_details = []
            
            for question1, question2 in related_question_pairs:
                if question1 in quantitative and question2 in quantitative:
                    val1 = quantitative[question1]
                    val2 = quantitative[question2]
                    
                    # Check for extreme opposite ratings (e.g., 5 and 1, or 4 and 1, or 5 and 2)
                    if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                        rating_diff = abs(val1 - val2)
                        if rating_diff >= 3:  # Significant difference (e.g., 5-1=4, 5-2=3, 4-1=3)
                            is_contradictory = True
                            contradiction_details.append({
                                "question_pair": f"{question1} vs {question2}",
                                "ratings": f"{val1} vs {val2}",
                                "difference": rating_diff
                            })
            
            # Also check for overall extreme variance in ratings
            if not is_contradictory:
                ratings = [v for v in quantitative.values() if isinstance(v, (int, float)) and 1 <= v <= 5]
                if len(ratings) >= 3:  # Need at least 3 ratings to check variance
                    min_rating = min(ratings)
                    max_rating = max(ratings)
                    if max_rating - min_rating >= 3:  # High variance indicates contradiction
                        is_contradictory = True
                        contradiction_details.append({
                            "question_pair": "overall_variance",
                            "ratings": f"min: {min_rating}, max: {max_rating}",
                            "difference": max_rating - min_rating
                        })
            
            if is_contradictory:
                contradictory_responses += 1
                polarization_details.append({
                    "participant": feedback.get('student_name', 'Anonymous'),
                    "contradictions": contradiction_details
                })
        
        # Calculate polarization score (percentage of contradictory responses)
        polarization_score = (contradictory_responses / total_responses * 100) if total_responses > 0 else 0.0
        
        # Determine polarization level
        if polarization_score >= 75:
            polarization_level = "high"
        elif polarization_score >= 50:
            polarization_level = "medium"
        else:
            polarization_level = "low"
        
        # Generate analysis summary
        if polarization_score == 0:
            analysis = "No polarization detected. Responses are consistent across all participants."
        elif polarization_level == "low":
            analysis = f"Low polarization detected ({polarization_score:.1f}%). Most participants provided consistent feedback."
        elif polarization_level == "medium":
            analysis = f"Medium polarization detected ({polarization_score:.1f}%). Some participants provided contradictory feedback that needs attention."
        else:
            analysis = f"High polarization detected ({polarization_score:.1f}%). Significant contradictory responses indicate potential issues with training delivery or content."
        
        return {
            "polarization_score": round(polarization_score, 2),
            "polarization_level": polarization_level,
            "contradictory_responses": contradictory_responses,
            "total_responses": total_responses,
            "analysis": analysis,
            "details": polarization_details[:10],  # Limit to first 10 for performance
            "recommendations": _get_polarization_recommendations(polarization_level, polarization_score)
        }
        
    except Exception as e:
        logger.error(f"Error computing polarization analysis: {e}")
        return {
            "polarization_score": 0.0,
            "polarization_level": "low",
            "contradictory_responses": 0,
            "total_responses": 0,
            "analysis": f"Error in polarization analysis: {str(e)}",
            "details": [],
            "recommendations": []
        }

def _get_polarization_recommendations(polarization_level: str, polarization_score: float) -> list:
    """Generate recommendations based on polarization level"""
    recommendations = []
    
    if polarization_level == "high":
        recommendations.extend([
            "Conduct follow-up interviews with participants to understand the reasons for contradictory feedback",
            "Review training content and delivery methods to identify potential confusion points",
            "Consider segmenting participants by experience level or background for future sessions",
            "Implement mid-session feedback collection to address issues in real-time"
        ])
    elif polarization_level == "medium":
        recommendations.extend([
            "Analyze specific question pairs where contradictions occur most frequently",
            "Consider providing clearer instructions or examples for rating criteria",
            "Follow up with participants who provided contradictory feedback for clarification"
        ])
    else:
        recommendations.extend([
            "Continue current training approach as feedback is generally consistent",
            "Monitor for any emerging patterns in future sessions"
        ])
    
    return recommendations

def _generate_enhanced_analysis(training_id, quantitative_insights, qualitative_analysis, total_feedbacks, polarization_analysis=None):
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

    # Include polarization analysis in enhanced analysis
    polarization_info = {}
    if polarization_analysis:
        polarization_info = {
            "polarization_score": polarization_analysis.get("polarization_score", 0),
            "polarization_level": polarization_analysis.get("polarization_level", "low"),
            "polarization_analysis": polarization_analysis.get("analysis", ""),
            "polarization_recommendations": polarization_analysis.get("recommendations", [])
        }
    
    return {
        "executive_summary": f"Processed {total_feedbacks} feedbacks for training {training_id}.",
        "overall_sentiment": qualitative_analysis.get("sentiment", "neutral"),
        "consensus_analysis": "Analysis complete",
        "key_strengths": qualitative_analysis.get("strengths", []),
        "critical_improvements": qualitative_analysis.get("concerns", []),
        "quantitative_insights": quantitative_insights,
        "polarization_detected": polarization_detected,
        "polarization_solutions": polarization_solutions,
        "polarization_check": polarization_info,
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

# -----------------------------
# Example usage
# -----------------------------
if __name__ == "__main__":
    test_feedback = "The training was good but could have been longer. Exercises were helpful."
    result = analyze_text_feedback(test_feedback)
    print(json.dumps(result, indent=2))
