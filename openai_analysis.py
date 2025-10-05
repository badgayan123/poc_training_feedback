"""
OpenAI Analysis Module for Training Feedback
This module provides AI-powered analysis of qualitative feedback using OpenAI GPT-4.
"""

import openai
from config import Config
import logging
import json
from typing import Dict, List, Optional
import re

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
                self.client = openai.OpenAI(api_key=Config.OPENAI_API_KEY)
        except Exception as e:
            logger.error(f"Error initializing OpenAI client: {e}")
            self.client = None
        
    def analyze_text_feedback(self, text: str) -> Dict[str, any]:
        """
        Analyze qualitative feedback text using OpenAI GPT-4.
        
        Args:
            text (str): The qualitative feedback text to analyze
            
        Returns:
            Dict containing:
                - summary: Concise summary of what the respondent is saying
                - sentiment: Overall tone (positive/neutral/negative)
                - suggestions: List of actionable improvement points
                - confidence: Analysis confidence score (0-1)
                - keywords: Key themes and topics mentioned
                
        Raises:
            ValueError: If text is empty or invalid
            Exception: If OpenAI API call fails
        """
        # Ensure client is initialized
        if self.client is None:
            self._initialize_client()
            
        # If client still not available, return fallback analysis
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
        
        # Clean and validate text
        text = text.strip()
        if len(text) < 10:
            raise ValueError("Text must be at least 10 characters long")
        
        try:
            # Create the analysis prompt
            prompt = self._create_analysis_prompt(text)
            
            # Call OpenAI API
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
            
            # Parse the response
            analysis_result = self._parse_openai_response(response.choices[0].message.content)
            
            # Add metadata
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
        """
        Create a structured prompt for OpenAI analysis.
        
        Args:
            text (str): The feedback text to analyze
            
        Returns:
            str: Formatted prompt for OpenAI
        """
        prompt = f"""
Analyze the following training feedback text and provide a structured analysis:

FEEDBACK TEXT:
"{text}"

Please analyze this feedback and respond with a JSON object containing exactly these fields:

1. "summary": A concise 2-3 sentence summary capturing what the respondent is saying, highlighting their key points and main concerns or praises.

2. "sentiment": Classify the overall tone as one of: "positive", "neutral", or "negative". Consider the overall emotional tone and satisfaction level.

3. "suggestions": Extract any actionable improvement points mentioned in the feedback. Return as an array of strings. If no suggestions are mentioned, return an empty array.

4. "keywords": Extract 3-5 key themes, topics, or concepts mentioned in the feedback. Return as an array of strings.

5. "strengths": Identify what the respondent liked or found valuable. Return as an array of strings.

6. "concerns": Identify any issues, problems, or areas of dissatisfaction mentioned. Return as an array of strings.

Focus on:
- What the respondent is actually saying (not assumptions)
- Actionable insights for training improvement
- Balanced analysis of both positive and negative aspects
- Clear, concise language

Respond with valid JSON only, no additional text.
"""
        return prompt
    
    def _parse_openai_response(self, response_content: str) -> Dict[str, any]:
        """
        Parse and validate the OpenAI response.
        
        Args:
            response_content (str): Raw response from OpenAI
            
        Returns:
            Dict: Parsed and validated analysis result
        """
        try:
            # Clean the response content
            response_content = response_content.strip()
            
            # Remove any markdown formatting if present
            if response_content.startswith('```json'):
                response_content = response_content[7:]
            if response_content.endswith('```'):
                response_content = response_content[:-3]
            
            # Parse JSON
            analysis = json.loads(response_content)
            
            # Validate required fields
            required_fields = ['summary', 'sentiment', 'suggestions', 'keywords', 'strengths', 'concerns']
            for field in required_fields:
                if field not in analysis:
                    analysis[field] = [] if field in ['suggestions', 'keywords', 'strengths', 'concerns'] else ""
            
            # Validate sentiment
            valid_sentiments = ['positive', 'neutral', 'negative']
            if analysis['sentiment'] not in valid_sentiments:
                analysis['sentiment'] = 'neutral'
            
            # Ensure arrays are lists
            for field in ['suggestions', 'keywords', 'strengths', 'concerns']:
                if not isinstance(analysis[field], list):
                    analysis[field] = []
            
            return analysis
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response as JSON: {e}")
            # Return fallback analysis
            return self._create_fallback_analysis(response_content)
        except Exception as e:
            logger.error(f"Error parsing OpenAI response: {e}")
            return self._create_fallback_analysis(response_content)
    
    def _create_fallback_analysis(self, response_content: str) -> Dict[str, any]:
        """
        Create a fallback analysis when OpenAI response parsing fails.
        
        Args:
            response_content (str): Raw response content
            
        Returns:
            Dict: Fallback analysis result
        """
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
        """
        Calculate confidence score for the analysis.
        
        Args:
            text (str): Original text
            analysis (Dict): Analysis result
            
        Returns:
            float: Confidence score between 0 and 1
        """
        confidence = 0.5  # Base confidence
        
        # Increase confidence based on text length
        if len(text) > 100:
            confidence += 0.2
        if len(text) > 300:
            confidence += 0.1
        
        # Increase confidence based on analysis completeness
        if analysis.get('summary') and len(analysis['summary']) > 20:
            confidence += 0.1
        if analysis.get('suggestions') and len(analysis['suggestions']) > 0:
            confidence += 0.1
        if analysis.get('keywords') and len(analysis['keywords']) > 0:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.utcnow().isoformat()
    
    def analyze_multiple_feedbacks(self, feedback_texts: List[str]) -> List[Dict[str, any]]:
        """
        Analyze multiple feedback texts in batch.
        
        Args:
            feedback_texts (List[str]): List of feedback texts to analyze
            
        Returns:
            List[Dict]: List of analysis results
        """
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
    """
    Convenience function to analyze a single feedback text.
    
    Args:
        text (str): The qualitative feedback text to analyze
        
    Returns:
        Dict: Analysis result containing summary, sentiment, suggestions, etc.
    """
    analyzer_instance = get_analyzer()
    return analyzer_instance.analyze_text_feedback(text)

def analyze_multiple_feedbacks(feedback_texts: List[str]) -> List[Dict[str, any]]:
    """
    Convenience function to analyze multiple feedback texts.
    
    Args:
        feedback_texts (List[str]): List of feedback texts to analyze
        
    Returns:
        List[Dict]: List of analysis results
    """
    analyzer_instance = get_analyzer()
    return analyzer_instance.analyze_multiple_feedbacks(feedback_texts)

# Example usage and testing
if __name__ == "__main__":
    # Test the analyzer
    test_feedback = """
    This training session was excellent! The instructor was very knowledgeable and engaging. 
    The content was highly relevant to my work and I learned a lot of practical skills. 
    However, I think the session could have been longer to cover more advanced topics. 
    The hands-on exercises were particularly helpful. I would recommend this training to my colleagues.
    """
    
    try:
        result = analyze_text_feedback(test_feedback)
        print("Analysis Result:")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}")

def analyze_comprehensive_training_feedback(training_id: str, all_feedbacks: list) -> dict:
    """
    Analyze all feedback for a training session with comprehensive insights.
    
    Args:
        training_id: The training session ID
        all_feedbacks: List of all feedback records for this training
        
    Returns:
        Dict containing comprehensive analysis results
    """
    try:
        # Get analyzer instance
        analyzer_instance = get_analyzer()
        
        # Ensure analyzer client is initialized
        if analyzer_instance.client is None:
            analyzer_instance._initialize_client()
            
        # Separate quantitative and qualitative data
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
        
        # Calculate quantitative statistics
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
        
        # Combine all qualitative feedback for AI analysis
        combined_qualitative = f"Training ID: {training_id}\n"
        combined_qualitative += f"Total Feedback Records: {len(all_feedbacks)}\n\n"
        combined_qualitative += "QUALITATIVE FEEDBACK FROM ALL PARTICIPANTS:\n\n"
        
        for i, qual_text in enumerate(qualitative_texts, 1):
            combined_qualitative += f"--- Participant {i} ---\n{qual_text}\n\n"
        
        # AI Analysis of qualitative data
        try:
            qualitative_analysis = analyzer_instance.analyze_text_feedback(combined_qualitative)
        except Exception as e:
            logger.error(f"Error in qualitative analysis: {e}")
            # Enhanced fallback analysis without OpenAI
            qualitative_analysis = {
                "summary": f"Analysis of {len(qualitative_texts)} qualitative feedback responses for training {training_id}. Feedback analysis completed using fallback method due to API limitations.",
                "sentiment": "neutral",
                "suggestions": ["Review individual feedback for detailed insights", "Consider upgrading OpenAI plan for enhanced analysis"],
                "keywords": ["training", "feedback", "evaluation", "analysis"],
                "strengths": ["Multiple participants provided feedback", "Comprehensive data collection"],
                "concerns": ["API quota exceeded - using fallback analysis"],
                "confidence": 0.6
            }
        
        # Calculate advanced statistics for smart analysis
        advanced_stats = {}
        if quantitative_insights:
            for metric, stats in quantitative_insights.items():
                distribution = stats.get('distribution', {})
                total_responses = stats.get('count', 0)
                
                if total_responses > 0:
                    poor_pct = (distribution.get('poor_1', 0) + distribution.get('fair_2', 0)) / total_responses * 100
                    good_pct = (distribution.get('good_3', 0) + distribution.get('very_good_4', 0)) / total_responses * 100
                    excellent_pct = distribution.get('excellent_5', 0) / total_responses * 100
                    
                    advanced_stats[metric] = {
                        'average': stats.get('average', 0),
                        'poor_percentage': round(poor_pct, 1),
                        'good_percentage': round(good_pct, 1),
                        'excellent_percentage': round(excellent_pct, 1),
                        'variance': stats.get('max', 0) - stats.get('min', 0),
                        'consensus_level': 'high' if stats.get('max', 0) - stats.get('min', 0) <= 2 else 'medium' if stats.get('max', 0) - stats.get('min', 0) <= 3 else 'low'
                    }

        # Debug logging
        logger.info(f"Processing {len(all_feedbacks)} feedback records for training {training_id}")
        logger.info(f"Quantitative data points: {len(quantitative_data)}")
        logger.info(f"Qualitative text responses: {len(qualitative_texts)}")
        logger.info(f"Advanced stats keys: {list(advanced_stats.keys())}")
        
        # Enhanced AI analysis with smart summarization
        enhanced_prompt = f"""Analyze this training feedback data for session {training_id}:

=== QUANTITATIVE RATINGS DATA ===
{json.dumps(advanced_stats, indent=2) if advanced_stats else "No quantitative data available"}

=== QUALITATIVE FEEDBACK TEXT ===
{combined_qualitative if combined_qualitative.strip() else "No qualitative feedback available"}

=== ANALYSIS INSTRUCTIONS ===
1. Use the ACTUAL data above to provide analysis
2. If quantitative data shows low averages (<2.5), indicate HIGH RISK
3. If there's high variance in ratings, detect POLARIZATION
4. Analyze the qualitative text for sentiment and themes
5. Provide actionable insights based on the real data
6. If polarization detected, provide specific solutions for handling disagreement

Respond with ONLY this JSON format (no other text):
{{
    "executive_summary": "Summary based on the actual data provided above",
    "overall_sentiment": "positive/neutral/negative/mixed",
    "consensus_analysis": "Analysis of agreement/disagreement patterns",
    "key_strengths": ["strength1", "strength2"],
    "critical_improvements": ["improvement1", "improvement2"],
    "quantitative_insights": "Analysis of the rating data shown above",
    "polarization_detected": true/false,
    "polarization_solutions": {{
        "root_causes": ["Specific data-driven causes with participant counts and metrics"],
        "immediate_actions": ["Targeted actions with specific participant groups and numbers"],
        "training_design_changes": ["Advanced adaptive learning solutions with parallel tracks"],
        "communication_strategies": ["Personalized communication with skill-level targeting"],
        "follow_up_actions": ["Predictive follow-up with success metrics and timelines"]
    }},
    "recommendations": ["rec1", "rec2", "rec3"],
    "risk_level": "high/medium/low",
    "priority_areas": ["area1", "area2"],
    "success_indicators": ["indicator1", "indicator2"],
    "confidence": 0.9
}}"""
        
        try:
            response = analyzer_instance.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert training evaluation analyst. Provide comprehensive insights combining quantitative and qualitative data."},
                    {"role": "user", "content": enhanced_prompt}
                ],
                temperature=0.2,
                max_tokens=1500
            )
            
            # Parse the response with error handling
            response_content = response.choices[0].message.content.strip()
            
            try:
                enhanced_analysis = json.loads(response_content)
            except json.JSONDecodeError as e:
                raise Exception(f"JSON parsing failed: {e}")
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            # Use enhanced fallback analysis
            enhanced_analysis = None
        
        # If OpenAI failed, use fallback analysis
        if enhanced_analysis is None:
            logger.info("Using fallback analysis due to OpenAI API issues")
            # Create smart fallback analysis with consensus detection
            overall_avg = 0
            poor_percentage = 0
            excellent_percentage = 0
            polarization_detected = False
            
            if quantitative_insights:
                all_averages = [stats.get('average', 0) for stats in quantitative_insights.values()]
                overall_avg = sum(all_averages) / len(all_averages) if all_averages else 0
                
                # Calculate overall poor/excellent percentages
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
            
            # Smart risk assessment
            risk_level = "low"
            if poor_percentage > 40 or overall_avg < 2.5:
                risk_level = "high"
            elif poor_percentage > 20 or overall_avg < 3.5:
                risk_level = "medium"
            
            # Smart sentiment detection
            if polarization_detected:
                sentiment = "mixed"
            elif overall_avg < 2.5:
                sentiment = "negative"
            elif overall_avg < 3.5:
                sentiment = "neutral"
            else:
                sentiment = "positive"
            
            # Create smart executive summary
            if polarization_detected:
                exec_summary = f"Training session {training_id} received polarized feedback from {len(all_feedbacks)} participants. Average rating: {overall_avg:.1f}/5. {poor_percentage:.1f}% gave poor ratings while {excellent_percentage:.1f}% gave excellent ratings, indicating significant disagreement among participants."
            elif overall_avg < 2.5:
                exec_summary = f"Training session {training_id} received consistently poor feedback from {len(all_feedbacks)} participants. Average rating: {overall_avg:.1f}/5 with {poor_percentage:.1f}% giving poor ratings, indicating significant issues requiring immediate attention."
            elif overall_avg > 4.0:
                exec_summary = f"Training session {training_id} received consistently positive feedback from {len(all_feedbacks)} participants. Average rating: {overall_avg:.1f}/5 with {excellent_percentage:.1f}% giving excellent ratings, indicating high satisfaction."
            else:
                exec_summary = f"Training session {training_id} received mixed feedback from {len(all_feedbacks)} participants. Average rating: {overall_avg:.1f}/5, indicating room for improvement in several areas."

            # Create enhanced polarization solutions with data-driven insights
            polarization_solutions = _create_enhanced_polarization_solutions(
                polarization_detected, quantitative_insights, overall_avg, 
                poor_percentage, excellent_percentage, len(all_feedbacks)
            )

            enhanced_analysis = {
                "executive_summary": exec_summary,
                "overall_sentiment": sentiment,
                "consensus_analysis": f"{'Polarized responses detected' if polarization_detected else 'Consistent feedback pattern'} - {'High variance in ratings' if polarization_detected else 'Low variance in ratings'}",
                "key_strengths": ["High participant engagement", "Comprehensive feedback received"] if len(all_feedbacks) > 5 else ["Multiple participants provided feedback"],
                "critical_improvements": ["Address low-rated areas", "Review training content and delivery"] if overall_avg < 3.5 else ["Continue monitoring feedback trends"],
                "quantitative_insights": f"Average rating: {overall_avg:.1f}/5. {poor_percentage:.1f}% poor ratings, {excellent_percentage:.1f}% excellent ratings. {'High polarization detected.' if polarization_detected else 'Consistent feedback pattern.'}",
                "polarization_detected": polarization_detected,
                "polarization_solutions": polarization_solutions,
                "recommendations": ["Address low-rated areas immediately", "Conduct follow-up sessions"] if overall_avg < 2.5 else ["Continue monitoring feedback trends", "Address any low-rated areas"],
                "risk_level": risk_level,
                "priority_areas": ["Overall satisfaction", "Content quality", "Trainer effectiveness"] if overall_avg < 3.5 else ["Overall satisfaction", "Content quality"],
                "success_indicators": ["Positive feedback trends", "High participation rates"] if overall_avg >= 3.5 else ["Improved ratings in future sessions", "Address current concerns"],
                "confidence": 0.7,
                "parsing_error": True,
                "raw_response": response_content[:200] + "..." if len(response_content) > 200 else response_content
            }
        
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
            # Add summary fields for easy access in frontend
            "summary": enhanced_analysis.get("executive_summary", "No summary available"),
            "sentiment": enhanced_analysis.get("overall_sentiment", "neutral"),
            "suggestions": enhanced_analysis.get("recommendations", ["No suggestions available"]),
            "risk_assessment": enhanced_analysis.get("risk_level", "medium"),
            "quantitative_analysis": quantitative_insights,
            # Include all individual feedback for detailed analysis
            "all_feedbacks": all_feedbacks
        }
        
    except Exception as e:
        logger.error(f"Error in analyze_comprehensive_training_feedback: {e}")
        raise Exception(f"Comprehensive analysis failed: {str(e)}")

def _create_enhanced_polarization_solutions(polarization_detected, quantitative_insights, overall_avg, poor_percentage, excellent_percentage, total_participants):
    """
    Create enhanced polarization solutions with data-driven insights
    """
    if not polarization_detected:
        return {
            "root_causes": ["Consistent participant feedback patterns"],
            "immediate_actions": ["Continue current approach"],
            "training_design_changes": ["Maintain current structure"],
            "communication_strategies": ["Continue current communication"],
            "follow_up_actions": ["Monitor feedback trends"]
        }
    
    # Analyze specific metrics for data-driven insights
    problematic_metrics = []
    strong_metrics = []
    
    if quantitative_insights:
        for metric, stats in quantitative_insights.items():
            if stats.get('average', 0) < 2.5:
                problematic_metrics.append(metric)
            elif stats.get('average', 0) > 4.0:
                strong_metrics.append(metric)
    
    # Calculate participant segments
    dissatisfied_count = int(total_participants * poor_percentage / 100)
    satisfied_count = int(total_participants * excellent_percentage / 100)
    neutral_count = total_participants - dissatisfied_count - satisfied_count
    
    # Enhanced root causes with data
    root_causes = [
        f"Skill level mismatch: {dissatisfied_count} participants struggled while {satisfied_count} excelled",
        f"Pace issues: Average rating {overall_avg:.1f}/5 indicates inconsistent pacing",
        f"Content complexity: {len(problematic_metrics)} areas consistently rated poorly",
        "Learning style conflicts: Visual vs auditory vs kinesthetic preferences",
        "Expectation misalignment: Different backgrounds and experience levels"
    ]
    
    # Immediate actions with specific targets
    immediate_actions = [
        f"Survey the {dissatisfied_count} dissatisfied participants: 'What specific topics were unclear?'",
        f"Interview the {satisfied_count} satisfied participants: 'What worked best for you?'",
        f"Create skill-level assessment for future sessions based on {total_participants} participants",
        f"Design targeted follow-up for {dissatisfied_count} struggling participants",
        f"Identify common themes in {len(problematic_metrics)} low-rated areas"
    ]
    
    # Advanced training design changes
    training_design_changes = [
        "Implement adaptive learning paths based on pre-assessment scores",
        f"Create parallel tracks: 'Beginner Track' (for {dissatisfied_count} participants) vs 'Advanced Track' (for {satisfied_count} participants)",
        "Add micro-learning modules for different skill levels",
        "Use blended learning: online + hands-on + peer mentoring",
        "Implement real-time feedback loops during training sessions",
        f"Design content complexity levels: Basic, Intermediate, Advanced for {total_participants} participants"
    ]
    
    # Smart communication strategies
    communication_strategies = [
        "Pre-training skill assessment and expectation setting",
        f"Personalized learning objectives for each of {total_participants} participants",
        "Real-time Q&A sessions with breakout groups by skill level",
        "Post-training individual coaching sessions for struggling participants",
        "Create learning communities for peer support and mentoring",
        f"Set clear success metrics for {dissatisfied_count} vs {satisfied_count} participant groups"
    ]
    
    # Predictive follow-up actions
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
