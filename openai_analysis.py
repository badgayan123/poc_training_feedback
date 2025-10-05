"""
OpenAI Analysis Module for Training Feedback
This module provides AI-powered analysis of qualitative feedback using OpenAI GPT-4.
"""

import openai
from config import Config
import logging
import json
from typing import Dict, List
import re
from datetime import datetime
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OpenAIFeedbackAnalyzer:
    """
    A class for analyzing qualitative feedback using OpenAI GPT-4.
    """
    
    def __init__(self):
        """Initialize the OpenAI client with API key from config."""
        self.client = None
        self.model = "gpt-4"
        self._initialize_client()
    
    def _initialize_client(self):
        """Lazy initialize the OpenAI client"""
        try:
            if self.client is None:
                # Proper v2.1.0 OpenAI API client usage
                openai.api_key = Config.OPENAI_API_KEY
                self.client = openai
        except Exception as e:
            logger.error(f"Error initializing OpenAI client: {e}")
            self.client = None
        
    def analyze_text_feedback(self, text: str) -> Dict[str, any]:
        """
        Analyze qualitative feedback text using OpenAI GPT-4.
        """
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
            
        except openai.error.OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise Exception(f"OpenAI API error: {str(e)}")
        except Exception as e:
            logger.error(f"Error analyzing feedback: {e}")
            raise Exception(f"Analysis failed: {str(e)}")
    
    def _create_analysis_prompt(self, text: str) -> str:
        """
        Create a structured prompt for OpenAI analysis.
        """
        prompt = f"""
Analyze the following training feedback text and provide a structured analysis:

FEEDBACK TEXT:
"{text}"

Please respond with a JSON object containing exactly these fields:
1. "summary": Concise 2-3 sentence summary
2. "sentiment": "positive", "neutral", or "negative"
3. "suggestions": List of actionable improvement points
4. "keywords": List of 3-5 key themes/topics
5. "strengths": Array of what was liked
6. "concerns": Array of issues mentioned

Respond with valid JSON only.
"""
        return prompt
    
    def _parse_openai_response(self, response_content: str) -> Dict[str, any]:
        """
        Parse and validate the OpenAI response.
        """
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
        if len(text) > 100: confidence += 0.2
        if len(text) > 300: confidence += 0.1
        if analysis.get('summary') and len(analysis['summary']) > 20: confidence += 0.1
        if analysis.get('suggestions') and len(analysis['suggestions']) > 0: confidence += 0.1
        if analysis.get('keywords') and len(analysis['keywords']) > 0: confidence += 0.1
        return min(confidence, 1.0)
    
    def _get_timestamp(self) -> str:
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

# Global analyzer instance
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
        
        # Quantitative insights
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
        for i, qual_text in enumerate(qualitative_texts, 1):
            combined_qualitative += f"--- Participant {i} ---\n{qual_text}\n\n"
        
        # AI analysis
        try:
            qualitative_analysis = analyzer_instance.analyze_text_feedback(combined_qualitative)
        except Exception as e:
            logger.error(f"Error in qualitative analysis: {e}")
            qualitative_analysis = {
                "summary": f"Analysis of {len(qualitative_texts)} feedback responses using fallback due to API issue.",
                "sentiment": "neutral",
                "suggestions": ["Review individual feedback manually"],
                "keywords": ["training", "feedback"],
                "strengths": ["Multiple participants provided feedback"],
                "concerns": ["API unavailable or quota exceeded"],
                "confidence": 0.6
            }
        
        # Advanced stats & fallback enhanced analysis
        enhanced_analysis = _create_enhanced_analysis(training_id, quantitative_insights, qualitative_analysis, len(all_feedbacks))
        
        return {
            "training_id": training_id,
            "total_participants": len(all_feedbacks),
            "qualitative_analysis": qualitative_analysis,
            "quantitative_insights": quantitative_insights,
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

def _create_enhanced_analysis(training_id, quantitative_insights, qualitative_analysis, total_participants):
    # Full enhanced analysis logic here...
    # Includes polarization detection, executive summary, risk level, recommendations
    # This can reuse the _create_enhanced_polarization_solutions function below
    overall_avg = 0
    poor_percentage = 0
    excellent_percentage = 0
    polarization_detected = False
    
    if quantitative_insights:
        all_averages = [stats.get('average', 0) for stats in quantitative_insights.values()]
        overall_avg = sum(all_averages) / len(all_averages) if all_averages else 0
        
        all_poor_pcts = []
        all_excellent_pcts = []
        all_variances = []
        for stats in quantitative_insights.values():
            distribution = stats.get('distribution', {})
            total_responses = stats.get('count', 0)
            if total_responses > 0:
                poor_pct = (distribution.get('poor_1', 0) + distribution.get('fair_2', 0)) / total_responses * 100
                excellent_pct = distribution.get('excellent_5', 0) / total_responses * 100
                variance = stats.get('max', 0) - stats.get('min', 0)
                all_poor_pcts.append(poor_pct)
                all_excellent_pcts.append(excellent_pct)
                all_variances.append(variance)
        if all_poor_pcts:
            poor_percentage = sum(all_poor_pcts) / len(all_poor_pcts)
            excellent_percentage = sum(all_excellent_pcts) / len(all_excellent_pcts)
            avg_variance = sum(all_variances) / len(all_variances)
            polarization_detected = avg_variance > 3 or (poor_percentage > 20 and excellent_percentage > 20)
    
    risk_level = "low"
    if poor_percentage > 40 or overall_avg < 2.5:
        risk_level = "high"
    elif poor_percentage > 20 or overall_avg < 3.5:
        risk_level = "medium"
    
    if polarization_detected:
        sentiment = "mixed"
    elif overall_avg < 2.5:
        sentiment = "negative"
    elif overall_avg < 3.5:
        sentiment = "neutral"
    else:
        sentiment = "positive"
    
    exec_summary = f"Training session {training_id} feedback summary based on actual data. Average rating: {overall_avg:.1f}/5."
    
    polarization_solutions = _create_enhanced_polarization_solutions(
        polarization_detected, quantitative_insights, overall_avg, poor_percentage, excellent_percentage, total_participants
    )
    
    return {
        "executive_summary": exec_summary,
        "overall_sentiment": sentiment,
        "consensus_analysis": f"{'Polarized responses detected' if polarization_detected else 'Consistent feedback pattern'}",
        "key_strengths": ["High participant engagement", "Comprehensive feedback received"] if total_participants > 5 else ["Multiple participants provided feedback"],
        "critical_improvements": ["Address low-rated areas", "Review training content and delivery"] if overall_avg < 3.5 else ["Continue monitoring feedback trends"],
        "quantitative_insights": f"Average rating: {overall_avg:.1f}/5. {poor_percentage:.1f}% poor ratings, {excellent_percentage:.1f}% excellent ratings.",
        "polarization_detected": polarization_detected,
        "polarization_solutions": polarization_solutions,
        "recommendations": ["Address low-rated areas immediately", "Conduct follow-up sessions"] if overall_avg < 2.5 else ["Continue monitoring feedback trends"],
        "risk_level": risk_level,
        "priority_areas": ["Overall satisfaction", "Content quality", "Trainer effectiveness"] if overall_avg < 3.5 else ["Overall satisfaction", "Content quality"],
        "success_indicators": ["Positive feedback trends", "High participation rates"] if overall_avg >= 3 else ["Participant improvement in next session"]
    }

def _create_enhanced_polarization_solutions(polarization_detected, quantitative_insights, overall_avg, poor_percentage, excellent_percentage, total_participants):
    """
    Full restored function with all your original attached parts
    """
    if not polarization_detected:
        return {
            "root_causes": ["Consistent participant feedback patterns"],
            "immediate_actions": ["Continue current approach"],
            "training_design_changes": ["Maintain current structure"],
            "communication_strategies": ["Continue current communication"],
            "follow_up_actions": ["Monitor feedback trends"]
        }
    
    problematic_metrics = []
    strong_metrics = []
    
    if quantitative_insights:
        for metric, stats in quantitative_insights.items():
            if stats.get('average', 0) < 2.5:
                problematic_metrics.append(metric)
            elif stats.get('average', 0) > 4.0:
                strong_metrics.append(metric)
    
    dissatisfied_count = int(total_participants * poor_percentage / 100)
    satisfied_count = int(total_participants * excellent_percentage / 100)
    neutral_count = total_participants - dissatisfied_count - satisfied_count
    
    root_causes = [
        f"Skill level mismatch: {dissatisfied_count} participants struggled while {satisfied_count} excelled",
        f"Pace issues: Average rating {overall_avg:.1f}/5 indicates inconsistent pacing",
        f"Content complexity: {len(problematic_metrics)} areas consistently rated poorly",
        "Learning style conflicts: Visual vs auditory vs kinesthetic preferences",
        "Expectation misalignment: Different backgrounds and experience levels"
    ]
    
    immediate_actions = [
        f"Survey the {dissatisfied_count} dissatisfied participants: 'What specific topics were unclear?'",
        f"Interview the {satisfied_count} satisfied participants: 'What worked best for you?'",
        f"Create skill-level assessment for future sessions based on {total_participants} participants",
        f"Design targeted follow-up for {dissatisfied_count} struggling participants",
        f"Identify common themes in {len(problematic_metrics)} low-rated areas"
    ]
    
    training_design_changes = [
        "Implement adaptive learning paths based on pre-assessment scores",
        f"Create parallel tracks: 'Beginner Track' (for {dissatisfied_count} participants) vs 'Advanced Track' (for {satisfied_count} participants)",
        "Add micro-learning modules for different skill levels",
        "Use blended learning: online + hands-on + peer mentoring",
        "Implement real-time feedback loops during training sessions",
        f"Design content complexity levels: Basic, Intermediate, Advanced for {total_participants} participants"
    ]
    
    communication_strategies = [
        "Pre-training skill assessment and expectation setting",
        f"Personalized learning objectives for each of {total_participants} participants",
        "Real-time Q&A sessions with breakout groups by skill level",
        "Post-training individual coaching sessions for struggling participants",
        "Create learning communities for peer support and mentoring",
        f"Set clear success metrics for {dissatisfied_count} vs {satisfied_count} participant groups"
    ]
    
    follow_up_actions = [
        f"Track learning outcomes over 30/60/90 days for {total_participants} participants",
        f"Create success metrics for {dissatisfied_count} struggling vs {satisfied_count} excelling groups",
        f"Design targeted refresher sessions based on {len(problematic_metrics)} problematic areas",
        "Implement peer mentoring programs pairing advanced with struggling participants",
        "Monitor job performance improvements and application success rates",
        f"Conduct follow-up surveys at 1, 3, and 6 months for {total_participants} participants"
    ]
    
    return {
        "root_causes": root_causes,
        "immediate_actions": immediate_actions,
        "training_design_changes": training_design_changes,
        "communication_strategies": communication_strategies,
        "follow_up_actions": follow_up_actions
    }
