"""
=========================================================
Urban Predictive Intelligence System
Social Media Event Detection Module
=========================================================

Social media analysis for detecting urban events:
- Twitter/X API integration for event detection
- Reddit API for community event discussions
- Telegram bot integration for local event monitoring
- Natural language processing for event classification
- Location-based event geotagging
- Real-time event discovery and alerting
- Integration with waste prediction system

Replaces the missing social media analysis capability.
=========================================================
"""

import os
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

# Try to import optional dependencies
try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False
    print("TextBlob not available - sentiment analysis disabled")

try:
    from geopy.geocoders import Nominatim
    from geopy.extra.rate_limiter import RateLimiter
    GEOPY_AVAILABLE = True
except ImportError:
    GEOPY_AVAILABLE = False
    print("Geopy not available - location geocoding disabled")

try:
    import tweepy
    TWITTER_AVAILABLE = True
except ImportError:
    TWITTER_AVAILABLE = False
    print("Tweepy not available - Twitter integration disabled")

try:
    import praw
    REDDIT_AVAILABLE = True
except ImportError:
    REDDIT_AVAILABLE = False
    print("PRAW not available - Reddit integration disabled")

try:
    from telegram import Update, Bot
    from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("python-telegram-bot not available - Telegram integration disabled")

# =========================================================
# CONFIGURATION
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "waste_module" / "data" / "processed"
OUTPUT_DIR = DATA_DIR / "social_events"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# API Configuration
TWITTER_CONFIG = {
    'api_key': os.getenv('TWITTER_API_KEY', ''),
    'api_secret': os.getenv('TWITTER_API_SECRET', ''),
    'access_token': os.getenv('TWITTER_ACCESS_TOKEN', ''),
    'access_secret': os.getenv('TWITTER_ACCESS_SECRET', ''),
    'bearer_token': os.getenv('TWITTER_BEARER_TOKEN', '')
}

REDDIT_CONFIG = {
    'client_id': os.getenv('REDDIT_CLIENT_ID', ''),
    'client_secret': os.getenv('REDDIT_CLIENT_SECRET', ''),
    'user_agent': 'UrbanPredictiveIntelligence/1.0'
}

TELEGRAM_CONFIG = {
    'bot_token': os.getenv('TELEGRAM_BOT_TOKEN', '')
}

# Location configuration
BENGALURU_KEYWORDS = [
    'bengaluru', 'bangalore', 'bangaluru', 'bengalore',
    'koramangala', 'indiranagar', 'jayanagar', 'malleshwaram',
    'whitefield', 'electronic city', 'hsr layout', 'btm layout'
]

EVENT_KEYWORDS = {
    'festival': ['festival', 'utsav', 'utsava', 'celebration', 'fair', 'mela', 'rath yatra'],
    'concert': ['concert', 'live music', 'performance', 'show', 'gig'],
    'sports': ['match', 'cricket', 'football', 'tournament', 'game', 'sports event'],
    'conference': ['conference', 'summit', 'meetup', 'seminar', 'workshop'],
    'protest': ['protest', 'rally', 'demonstration', 'march', 'strike'],
    'market': ['market', 'fair', 'flea market', 'exhibition', 'expo'],
    'religious': ['temple', 'festival', 'puja', 'jatra', 'religious event'],
    'political': ['rally', 'meeting', 'campaign', 'political event']
}

# =========================================================
# NLP EVENT CLASSIFIER
# =========================================================

class EventClassifier:
    """Classify social media posts as events or non-events."""
    
    def __init__(self):
        if GEOPY_AVAILABLE:
            self.geocoder = Nominatim(user_agent="urban_intelligence")
            self.geocode = RateLimiter(self.geocoder.geocode, min_delay_seconds=1)
        else:
            self.geocoder = None
            self.geocode = None
    
    def extract_event_type(self, text: str) -> str:
        """Extract event type from text using keyword matching."""
        text_lower = text.lower()
        
        for event_type, keywords in EVENT_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return event_type
        
        return 'other'
    
    def extract_location(self, text: str) -> Optional[Dict]:
        """Extract location information from text."""
        # Check for Bengaluru-specific keywords
        for keyword in BENGALURU_KEYWORDS:
            if keyword.lower() in text.lower():
                return {
                    'city': 'Bengaluru',
                    'area': keyword if keyword not in ['bengaluru', 'bangalore'] else None,
                    'confidence': 0.8
                }
        
        # Try geocoding
        try:
            location = self.geocode(text)
            if location:
                return {
                    'city': location.raw.get('address', {}).get('city', 'Unknown'),
                    'area': location.raw.get('address', {}).get('suburb', None),
                    'latitude': location.latitude,
                    'longitude': location.longitude,
                    'confidence': 0.6
                }
        except:
            pass
        
        return None
    
    def extract_date(self, text: str) -> Optional[datetime]:
        """Extract date information from text."""
        # Simple date extraction patterns
        date_patterns = [
            r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # DD/MM/YYYY or DD-MM-YYYY
            r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',  # YYYY/MM/DD
            r'(?:today|tomorrow|yesterday)',  # Relative dates
            r'(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)',  # Day names
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    # Try to parse the date
                    date_str = match.group()
                    if 'today' in date_str.lower():
                        return datetime.now()
                    elif 'tomorrow' in date_str.lower():
                        return datetime.now() + timedelta(days=1)
                    elif 'yesterday' in date_str.lower():
                        return datetime.now() - timedelta(days=1)
                    else:
                        # Try standard date parsing
                        for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d', '%Y-%m-%d']:
                            try:
                                return datetime.strptime(date_str, fmt)
                            except ValueError:
                                continue
                except:
                    continue
        
        return None
    
    def calculate_event_intensity(self, text: str, engagement_metrics: Dict) -> int:
        """Calculate event intensity based on text and engagement."""
        intensity = 1  # Base intensity
        
        # Text-based intensity
        text_lower = text.lower()
        if any(word in text_lower for word in ['grand', 'massive', 'huge', 'major']):
            intensity += 1
        if any(word in text_lower for word in ['international', 'national', 'city-wide']):
            intensity += 1
        
        # Engagement-based intensity
        likes = engagement_metrics.get('likes', 0)
        shares = engagement_metrics.get('shares', 0)
        comments = engagement_metrics.get('comments', 0)
        
        total_engagement = likes + shares * 2 + comments * 3
        
        if total_engagement > 1000:
            intensity += 1
        if total_engagement > 5000:
            intensity += 1
        
        return min(intensity, 3)  # Max intensity level 3

# =========================================================
# TWITTER EVENT DETECTOR
# =========================================================

class TwitterEventDetector:
    """Detect events from Twitter/X data."""
    
    def __init__(self, config: Dict = None):
        self.config = config or TWITTER_CONFIG
        self.classifier = EventClassifier()
        self.client = None
        
        if not TWITTER_AVAILABLE:
            print("Twitter integration not available - tweepy not installed")
            return
            
        if self.config['bearer_token']:
            try:
                self.client = tweepy.Client(bearer_token=self.config['bearer_token'])
            except Exception as e:
                print(f"Twitter API initialization failed: {e}")
    
    def search_events(self, query: str, max_results: int = 100) -> List[Dict]:
        """Search Twitter for event-related tweets."""
        if not self.client:
            print("Twitter client not initialized")
            return []
        
        try:
            # Build search query with Bengaluru keywords
            bengaluru_query = f"({query}) AND ({' OR '.join(BENGALURU_KEYWORDS)})"
            
            tweets = self.client.search_recent_tweets(
                query=bengaluru_query,
                max_results=max_results,
                tweet_fields=['created_at', 'public_metrics', 'geo', 'entities']
            )
            
            events = []
            for tweet in tweets:
                tweet_data = {
                    'platform': 'twitter',
                    'post_id': tweet.id,
                    'text': tweet.text,
                    'created_at': tweet.created_at.isoformat() if tweet.created_at else None,
                    'author_id': tweet.author_id,
                    'engagement_metrics': {
                        'likes': tweet.public_metrics['like_count'] if tweet.public_metrics else 0,
                        'shares': tweet.public_metrics['retweet_count'] if tweet.public_metrics else 0,
                        'comments': tweet.public_metrics['reply_count'] if tweet.public_metrics else 0
                    },
                    'url': f"https://twitter.com/i/web/status/{tweet.id}"
                }
                
                # Classify event
                event_type = self.classifier.extract_event_type(tweet.text)
                location = self.classifier.extract_location(tweet.text)
                date = self.classifier.extract_date(tweet.text)
                intensity = self.classifier.calculate_event_intensity(
                    tweet.text, 
                    tweet_data['engagement_metrics']
                )
                
                if event_type != 'other' or location:
                    tweet_data.update({
                        'event_type': event_type,
                        'location': location,
                        'event_date': date.isoformat() if date else None,
                        'intensity': intensity
                    })
                    events.append(tweet_data)
            
            return events
            
        except Exception as e:
            print(f"Twitter search error: {e}")
            return []

# =========================================================
# REDDIT EVENT DETECTOR
# =========================================================

class RedditEventDetector:
    """Detect events from Reddit discussions."""
    
    def __init__(self, config: Dict = None):
        self.config = config or REDDIT_CONFIG
        self.classifier = EventClassifier()
        self.reddit = None
        
        if not REDDIT_AVAILABLE:
            print("Reddit integration not available - praw not installed")
            return
            
        if self.config['client_id'] and self.config['client_secret']:
            try:
                self.reddit = praw.Reddit(
                    client_id=self.config['client_id'],
                    client_secret=self.config['client_secret'],
                    user_agent=self.config['user_agent']
                )
            except Exception as e:
                print(f"Reddit API initialization failed: {e}")
    
    def search_subreddits(self, subreddit_names: List[str], limit: int = 50) -> List[Dict]:
        """Search Reddit subreddits for event-related posts."""
        if not self.reddit:
            print("Reddit client not initialized")
            return []
        
        events = []
        
        for subreddit_name in subreddit_names:
            try:
                subreddit = self.reddit.subreddit(subreddit_name)
                
                for post in subreddit.new(limit=limit):
                    post_data = {
                        'platform': 'reddit',
                        'post_id': post.id,
                        'text': f"{post.title}\n{post.selftext}",
                        'created_at': datetime.fromtimestamp(post.created_utc).isoformat(),
                        'author': str(post.author),
                        'engagement_metrics': {
                            'likes': post.score,
                            'comments': post.num_comments,
                            'shares': 0  # Reddit doesn't have native shares
                        },
                        'url': post.url,
                        'subreddit': subreddit_name
                    }
                    
                    # Check for Bengaluru relevance
                    if any(keyword in post_data['text'].lower() for keyword in BENGALURU_KEYWORDS):
                        # Classify event
                        event_type = self.classifier.extract_event_type(post_data['text'])
                        location = self.classifier.extract_location(post_data['text'])
                        date = self.classifier.extract_date(post_data['text'])
                        intensity = self.classifier.calculate_event_intensity(
                            post_data['text'],
                            post_data['engagement_metrics']
                        )
                        
                        if event_type != 'other' or location:
                            post_data.update({
                                'event_type': event_type,
                                'location': location,
                                'event_date': date.isoformat() if date else None,
                                'intensity': intensity
                            })
                            events.append(post_data)
                
            except Exception as e:
                print(f"Error searching subreddit {subreddit_name}: {e}")
                continue
        
        return events

# =========================================================
# TELEGRAM EVENT MONITOR
# =========================================================

class TelegramEventMonitor:
    """Monitor Telegram channels for local events."""
    
    def __init__(self, config: Dict = None):
        self.config = config or TELEGRAM_CONFIG
        self.classifier = EventClassifier()
        self.bot = None
        self.monitored_channels = []
        self.detected_events = []
        
        if self.config['bot_token']:
            try:
                self.bot = Bot(token=self.config['bot_token'])
            except Exception as e:
                print(f"Telegram bot initialization failed: {e}")
    
    def monitor_channel(self, channel_id: str, limit: int = 20) -> List[Dict]:
        """Monitor a Telegram channel for event-related messages."""
        if not self.bot:
            print("Telegram bot not initialized")
            return []
        
        events = []
        
        try:
            # Get updates from the channel
            updates = self.bot.get_updates(timeout=10)
            
            for update in updates:
                if update.message and update.message.chat:
                    message = update.message
                    
                    # Check if message is from monitored channel
                    if str(message.chat.id) == channel_id:
                        message_data = {
                            'platform': 'telegram',
                            'post_id': message.message_id,
                            'text': message.text or message.caption or '',
                            'created_at': message.date.isoformat() if message.date else None,
                            'author': message.from_user.username if message.from_user else 'unknown',
                            'engagement_metrics': {
                                'views': getattr(message, 'views', 0),
                                'forwards': getattr(message, 'forwards', 0)
                            },
                            'channel_id': channel_id,
                            'channel_name': message.chat.title
                        }
                        
                        # Check for Bengaluru relevance
                        if any(keyword in message_data['text'].lower() for keyword in BENGALURU_KEYWORDS):
                            # Classify event
                            event_type = self.classifier.extract_event_type(message_data['text'])
                            location = self.classifier.extract_location(message_data['text'])
                            date = self.classifier.extract_date(message_data['text'])
                            intensity = self.classifier.calculate_event_intensity(
                                message_data['text'],
                                message_data['engagement_metrics']
                            )
                            
                            if event_type != 'other' or location:
                                message_data.update({
                                    'event_type': event_type,
                                    'location': location,
                                    'event_date': date.isoformat() if date else None,
                                    'intensity': intensity
                                })
                                events.append(message_data)
        
        except Exception as e:
            print(f"Error monitoring Telegram channel {channel_id}: {e}")
        
        return events

# =========================================================
# SOCIAL MEDIA AGGREGATOR
# =========================================================

class SocialMediaEventAggregator:
    """Aggregate events from multiple social media platforms."""
    
    def __init__(self):
        self.twitter_detector = TwitterEventDetector()
        self.reddit_detector = RedditEventDetector()
        self.telegram_monitor = TelegramEventMonitor()
    
    def collect_all_events(self) -> List[Dict]:
        """Collect events from all available platforms."""
        print("Collecting social media events...")
        
        all_events = []
        
        # Twitter events
        print("Searching Twitter...")
        twitter_events = self.twitter_detector.search_events("event OR festival OR concert", max_results=50)
        all_events.extend(twitter_events)
        print(f"Found {len(twitter_events)} Twitter events")
        
        # Reddit events
        print("Searching Reddit...")
        bengaluru_subreddits = ['bangalore', 'Bengaluru', 'india']
        reddit_events = self.reddit_detector.search_subreddits(bengaluru_subreddits, limit=30)
        all_events.extend(reddit_events)
        print(f"Found {len(reddit_events)} Reddit events")
        
        # Telegram events (if channels are configured)
        if self.telegram_monitor.monitored_channels:
            print("Monitoring Telegram...")
            for channel_id in self.telegram_monitor.monitored_channels:
                telegram_events = self.telegram_monitor.monitor_channel(channel_id)
                all_events.extend(telegram_events)
            print(f"Found {len(telegram_events)} Telegram events")
        
        return all_events
    
    def deduplicate_events(self, events: List[Dict]) -> List[Dict]:
        """Remove duplicate events based on similarity."""
        unique_events = []
        seen_signatures = set()
        
        for event in events:
            # Create a signature for deduplication
            signature = f"{event['platform']}_{event['event_type']}_{hash(event['text'][:100])}"
            
            if signature not in seen_signatures:
                seen_signatures.add(signature)
                unique_events.append(event)
        
        return unique_events
    
    def standardize_events(self, events: List[Dict]) -> pd.DataFrame:
        """Standardize event data format."""
        standardized = []
        
        for event in events:
            standardized_event = {
                'event_id': f"{event['platform']}_{event['post_id']}",
                'platform': event['platform'],
                'event_type': event.get('event_type', 'other'),
                'text': event['text'][:500],  # Truncate long text
                'created_at': event['created_at'],
                'author': event.get('author', 'unknown'),
                'intensity': event.get('intensity', 1),
                'url': event.get('url', ''),
                'location_city': event.get('location', {}).get('city') if event.get('location') else None,
                'location_area': event.get('location', {}).get('area') if event.get('location') else None,
                'location_lat': event.get('location', {}).get('latitude') if event.get('location') else None,
                'location_lon': event.get('location', {}).get('longitude') if event.get('location') else None,
                'event_date': event.get('event_date'),
                'engagement_score': (
                    event['engagement_metrics']['likes'] + 
                    event['engagement_metrics'].get('shares', 0) * 2 + 
                    event['engagement_metrics'].get('comments', 0) * 3
                )
            }
            standardized.append(standardized_event)
        
        return pd.DataFrame(standardized)
    
    def filter_relevant_events(self, events_df: pd.DataFrame) -> pd.DataFrame:
        """Filter events relevant to waste prediction."""
        # Keep events that are likely to generate waste
        waste_generating_types = ['festival', 'concert', 'market', 'religious', 'sports']
        
        # Filter by location (Bengaluru)
        bengaluru_events = events_df[
            (events_df['location_city'] == 'Bengaluru') |
            (events_df['location_area'].isin(BENGALURU_KEYWORDS))
        ]
        
        # Filter by event type
        relevant_events = bengaluru_events[
            bengaluru_events['event_type'].isin(waste_generating_types) |
            (bengaluru_events['intensity'] >= 2)
        ]
        
        return relevant_events
    
    def generate_event_impact_estimates(self, events_df: pd.DataFrame) -> pd.DataFrame:
        """Generate waste impact estimates for detected events."""
        # Define impact factors based on event type and intensity
        impact_factors = {
            'festival': 2.0,
            'concert': 1.5,
            'market': 1.3,
            'religious': 1.8,
            'sports': 1.4,
            'conference': 1.2,
            'other': 1.1
        }
        
        # Apply intensity multiplier
        intensity_multipliers = {1: 1.0, 2: 1.3, 3: 1.6}
        
        def calculate_impact(row):
            base_impact = impact_factors.get(row['event_type'], 1.1)
            intensity_mult = intensity_multipliers.get(row['intensity'], 1.0)
            engagement_factor = min(row['engagement_score'] / 1000, 2.0)
            
            total_impact = base_impact * intensity_mult * (1 + engagement_factor * 0.1)
            return min(total_impact, 3.0)  # Cap at 3x impact
        
        events_df['estimated_waste_impact'] = events_df.apply(calculate_impact, axis=1)
        
        return events_df

# =========================================================
# MAIN EXECUTION
# =========================================================

def main():
    print("=" * 70)
    print("SOCIAL MEDIA EVENT DETECTION MODULE")
    print("=" * 70)
    
    # Initialize aggregator
    aggregator = SocialMediaEventAggregator()
    
    # Collect events
    raw_events = aggregator.collect_all_events()
    print(f"\nTotal raw events collected: {len(raw_events)}")
    
    # Deduplicate
    unique_events = aggregator.deduplicate_events(raw_events)
    print(f"Unique events after deduplication: {len(unique_events)}")
    
    # Standardize
    events_df = aggregator.standardize_events(unique_events)
    print(f"Standardized events: {len(events_df)}")
    
    # Filter relevant events
    relevant_events = aggregator.filter_relevant_events(events_df)
    print(f"Relevant events for waste prediction: {len(relevant_events)}")
    
    # Generate impact estimates
    final_events = aggregator.generate_event_impact_estimates(relevant_events)
    
    # Save results
    output_file = OUTPUT_DIR / "social_media_events.csv"
    final_events.to_csv(output_file, index=False)
    print(f"\nSocial media events saved to: {output_file}")
    
    # Print summary
    print("\n" + "=" * 70)
    print("SOCIAL MEDIA EVENT DETECTION SUMMARY")
    print("=" * 70)
    
    print(f"\nTotal detected events: {len(final_events)}")
    print(f"Platforms: {final_events['platform'].value_counts().to_dict()}")
    print(f"Event types: {final_events['event_type'].value_counts().to_dict()}")
    print(f"Intensity distribution: {final_events['intensity'].value_counts().to_dict()}")
    
    print("\nTop 10 events by impact:")
    top_events = final_events.nlargest(10, 'estimated_waste_impact')
    for _, event in top_events.iterrows():
        print(f"  {event['event_type']} - Impact: {event['estimated_waste_impact']:.2f}x")
        print(f"    Location: {event['location_area'] or event['location_city']}")
        print(f"    Text: {event['text'][:100]}...")
        print()
    
    print("=" * 70)
    print("SOCIAL MEDIA EVENT DETECTION COMPLETED")
    print("=" * 70)

if __name__ == "__main__":
    main()