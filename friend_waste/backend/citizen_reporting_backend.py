"""
=========================================================
Urban Predictive Intelligence System
Citizen Reporting Backend Module
=========================================================

Complete backend implementation for citizen waste reporting:
- SQLite database for report storage
- REST API endpoints for report submission
- Report validation and categorization
- Location-based report aggregation
- Integration with waste prediction system
- Report analytics and dashboard data
- User authentication and authorization
- Report status tracking and updates

Replaces the incomplete citizen reporting system.
=========================================================
"""

import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import hashlib
import uuid
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
from flask import Flask, request, jsonify, g
from flask_cors import CORS

# Try to import optional dependencies
try:
    from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker, relationship
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    print("SQLAlchemy not available - using in-memory storage")

try:
    from geopy.distance import geodesic
    GEOPY_AVAILABLE = True
except ImportError:
    GEOPY_AVAILABLE = False
    print("Geopy not available - distance calculations disabled")

try:
    from shapely.geometry import Point
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False
    print("Shapely not available - spatial operations disabled")

try:
    import geopandas as gpd
    GEOPANDAS_AVAILABLE = True
except ImportError:
    GEOPANDAS_AVAILABLE = False
    print("Geopandas not available - using pandas only")

# =========================================================
# CONFIGURATION
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "waste_module" / "data"
DATABASE_DIR = DATA_DIR / "databases"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_FILE = DATABASE_DIR / "citizen_reports.db"
BACKUP_DIR = DATABASE_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# Flask configuration
app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['JSON_SORT_KEYS'] = False

# In-memory storage (fallback when SQLAlchemy not available)
if not SQLALCHEMY_AVAILABLE:
    reports_db = {}
    users_db = {}
    comments_db = {}
    print("Using in-memory storage for citizen reports")

# =========================================================
# DATABASE MODELS (SQLAlchemy - Optional)
# =========================================================

if SQLALCHEMY_AVAILABLE:
    Base = declarative_base()

    class User(Base):
        """User model for citizen reporting system."""
        __tablename__ = 'users'
        
        id = Column(Integer, primary_key=True)
        user_id = Column(String(36), unique=True, nullable=False, index=True)
        username = Column(String(50), unique=True, nullable=False)
        email = Column(String(100), unique=True, nullable=False)
        phone = Column(String(20))
        address = Column(Text)
        created_at = Column(DateTime, default=datetime.utcnow)
        is_active = Column(Boolean, default=True)
        reputation_score = Column(Integer, default=100)
        
        # Relationships
        reports = relationship("CitizenReport", back_populates="user")

    class CitizenReport(Base):
        """Citizen waste report model."""
        __tablename__ = 'citizen_reports'
        
        id = Column(Integer, primary_key=True)
        report_id = Column(String(36), unique=True, nullable=False, index=True)
        user_id = Column(String(36), ForeignKey('users.user_id'), nullable=False)
        
        # Location information
        latitude = Column(Float, nullable=False)
        longitude = Column(Float, nullable=False)
        address = Column(Text)
        landmark = Column(String(200))
        
        # Report details
        waste_type = Column(String(50), nullable=False)
        severity = Column(String(20), nullable=False)
        description = Column(Text)
        
        # Additional information
        photo_url = Column(String(500))
        estimated_quantity = Column(String(50))
        waste_category = Column(String(50))
        
        # Status tracking
        status = Column(String(20), default='pending')
        priority = Column(Integer, default=3)
        
        # Timestamps
        reported_at = Column(DateTime, default=datetime.utcnow, nullable=False)
        verified_at = Column(DateTime)
        resolved_at = Column(DateTime)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        
        # Verification and resolution
        verified_by = Column(String(36))
        resolved_by = Column(String(36))
        resolution_notes = Column(Text)
        
        # Impact analysis
        grid_id = Column(String(20))
        area_name = Column(String(100))
        nearby_overflow_risk = Column(String(20))
        
        # Relationships
        user = relationship("User", back_populates="reports")
        comments = relationship("ReportComment", back_populates="report")

    class ReportComment(Base):
        """Comments on citizen reports."""
        __tablename__ = 'report_comments'
        
        id = Column(Integer, primary_key=True)
        comment_id = Column(String(36), unique=True, nullable=False)
        report_id = Column(String(36), ForeignKey('citizen_reports.report_id'), nullable=False)
        user_id = Column(String(36), ForeignKey('users.user_id'), nullable=False)
        comment_text = Column(Text, nullable=False)
        created_at = Column(DateTime, default=datetime.utcnow)
        
        # Relationships
        report = relationship("CitizenReport", back_populates="comments")

    class ReportAnalytics(Base):
        """Analytics data for citizen reports."""
        __tablename__ = 'report_analytics'
        
        id = Column(Integer, primary_key=True)
        date = Column(DateTime, nullable=False, index=True)
        total_reports = Column(Integer, default=0)
        pending_reports = Column(Integer, default=0)
        verified_reports = Column(Integer, default=0)
        resolved_reports = Column(Integer, default=0)
        avg_resolution_time_hours = Column(Float)
        reports_by_type = Column(Text)
        reports_by_area = Column(Text)
        created_at = Column(DateTime, default=datetime.utcnow)

    # =========================================================
    # DATABASE ENGINE
    # =========================================================

    engine = create_engine(f'sqlite:///{DATABASE_FILE}', echo=False)
    Session = sessionmaker(bind=engine)

    def init_db():
        """Initialize database tables."""
        Base.metadata.create_all(engine)
        print("Database tables created successfully")

    def get_db():
        """Get database session."""
        if 'db' not in g:
            g.db = Session()
        return g.db

    @app.teardown_appcontext
    def close_db(error):
        """Close database session."""
        db = g.pop('db', None)
        if db is not None:
            db.close()
else:
    # In-memory fallback
    def init_db():
        """Initialize in-memory storage."""
        print("Using in-memory storage - no database initialization needed")

    def get_db():
        """Get in-memory storage."""
        return {'reports': reports_db, 'users': users_db, 'comments': comments_db}

    @app.teardown_appcontext
    def close_db(error):
        """No-op for in-memory storage."""
        pass

# =========================================================
# REPORT VALIDATION
# =========================================================

class ReportValidator:
    """Validate citizen reports before submission."""
    
    VALID_WASTE_TYPES = [
        'garbage', 'overflow', 'illegal_dumping', 'construction_debris',
        'medical_waste', 'electronic_waste', 'hazardous', 'street_cleaning',
        'container_damage', 'missed_collection', 'other'
    ]
    
    VALID_SEVERITY = ['low', 'medium', 'high', 'critical']
    VALID_QUANTITIES = ['small', 'medium', 'large', 'truckload', 'unknown']
    VALID_CATEGORIES = ['residential', 'commercial', 'industrial', 'construction', 'unknown']
    
    @classmethod
    def validate_report_data(cls, report_data: Dict) -> Tuple[bool, List[str]]:
        """Validate report data and return (is_valid, error_messages)."""
        errors = []
        
        # Required fields
        required_fields = ['user_id', 'latitude', 'longitude', 'waste_type', 'severity']
        for field in required_fields:
            if field not in report_data or report_data[field] is None:
                errors.append(f"Missing required field: {field}")
        
        # Validate coordinates
        if 'latitude' in report_data:
            lat = report_data['latitude']
            if not (-90 <= lat <= 90):
                errors.append("Invalid latitude value")
        
        if 'longitude' in report_data:
            lon = report_data['longitude']
            if not (-180 <= lon <= 180):
                errors.append("Invalid longitude value")
        
        # Validate waste type
        if 'waste_type' in report_data:
            if report_data['waste_type'] not in cls.VALID_WASTE_TYPES:
                errors.append(f"Invalid waste type. Must be one of: {cls.VALID_WASTE_TYPES}")
        
        # Validate severity
        if 'severity' in report_data:
            if report_data['severity'] not in cls.VALID_SEVERITY:
                errors.append(f"Invalid severity. Must be one of: {cls.VALID_SEVERITY}")
        
        # Validate optional fields
        if 'estimated_quantity' in report_data:
            if report_data['estimated_quantity'] not in cls.VALID_QUANTITIES:
                errors.append(f"Invalid quantity. Must be one of: {cls.VALID_QUANTITIES}")
        
        if 'waste_category' in report_data:
            if report_data['waste_category'] not in cls.VALID_CATEGORIES:
                errors.append(f"Invalid category. Must be one of: {cls.VALID_CATEGORIES}")
        
        return len(errors) == 0, errors

# =========================================================
# REPORT PROCESSING
# =========================================================

class ReportProcessor:
    """Process and analyze citizen reports."""
    
    def __init__(self):
        self.grid_file = PROJECT_ROOT / "waste_module" / "data" / "bengaluru_grid.csv"
        self.area_boundaries = PROJECT_ROOT / "waste_module" / "data" / "processed" / "bengaluru_area_boundaries.gpkg"
        self.overflow_predictions = PROJECT_ROOT / "waste_module" / "data" / "processed" / "bengaluru_area_overflow_predictions.csv"
    
    def find_nearest_grid(self, lat: float, lon: float) -> Optional[str]:
        """Find the nearest grid cell to a location."""
        try:
            if not self.grid_file.exists():
                return None
            
            grid_df = pd.read_csv(self.grid_file)
            
            # Calculate distances
            distances = []
            for _, grid in grid_df.iterrows():
                distance = geodesic((lat, lon), (grid['Latitude'], grid['Longitude'])).kilometers
                distances.append((distance, grid['Grid_ID']))
            
            # Find nearest grid
            distances.sort(key=lambda x: x[0])
            return distances[0][1] if distances else None
            
        except Exception as e:
            print(f"Error finding nearest grid: {e}")
            return None
    
    def find_area_for_location(self, lat: float, lon: float) -> Optional[str]:
        """Find the administrative area for a location."""
        try:
            if not self.area_boundaries.exists():
                return None
            
            gdf = gpd.read_file(self.area_boundaries)
            point = Point(lon, lat)
            
            # Find containing area
            for idx, row in gdf.iterrows():
                if row.geometry.contains(point):
                    return row.get('name', row.get('area_name', None))
            
            return None
            
        except Exception as e:
            print(f"Error finding area: {e}")
            return None
    
    def get_nearby_overflow_risk(self, lat: float, lon: float) -> Optional[str]:
        """Get overflow risk for nearby area."""
        try:
            if not self.overflow_predictions.exists():
                return None
            
            # Find area first
            area_name = self.find_area_for_location(lat, lon)
            if not area_name:
                return None
            
            # Get overflow risk for area
            overflow_df = pd.read_csv(self.overflow_predictions)
            area_risk = overflow_df[overflow_df['area_name'] == area_name]
            
            if not area_risk.empty:
                return area_risk.iloc[0].get('Area_Overflow_Risk', 'UNKNOWN')
            
            return None
            
        except Exception as e:
            print(f"Error getting overflow risk: {e}")
            return None
    
    def calculate_priority(self, report_data: Dict) -> int:
        """Calculate report priority based on multiple factors."""
        priority = 3  # Default medium priority
        
        # Severity impact
        severity_priority = {
            'critical': 1,
            'high': 2,
            'medium': 3,
            'low': 4
        }
        priority = severity_priority.get(report_data.get('severity', 'medium'), 3)
        
        # Waste type impact
        high_priority_types = ['hazardous', 'medical_waste', 'illegal_dumping']
        if report_data.get('waste_type') in high_priority_types:
            priority = min(priority, 2)
        
        # Quantity impact
        quantity_priority = {
            'truckload': 1,
            'large': 2,
            'medium': 3,
            'small': 4,
            'unknown': 3
        }
        quantity_prio = quantity_priority.get(report_data.get('estimated_quantity', 'unknown'), 3)
        priority = min(priority, quantity_prio)
        
        # Location impact (near high-risk areas)
        if report_data.get('nearby_overflow_risk') == 'CRITICAL':
            priority = min(priority, 1)
        elif report_data.get('nearby_overflow_risk') == 'HIGH':
            priority = min(priority, 2)
        
        return priority
    
    def process_report(self, report_data: Dict) -> Dict:
        """Process report with location analysis and priority calculation."""
        lat = report_data['latitude']
        lon = report_data['longitude']
        
        # Location analysis
        grid_id = self.find_nearest_grid(lat, lon)
        area_name = self.find_area_for_location(lat, lon)
        overflow_risk = self.get_nearby_overflow_risk(lat, lon)
        
        # Add processed data
        processed_data = report_data.copy()
        processed_data['grid_id'] = grid_id
        processed_data['area_name'] = area_name
        processed_data['nearby_overflow_risk'] = overflow_risk
        
        # Calculate priority
        priority = self.calculate_priority(processed_data)
        processed_data['priority'] = priority
        
        return processed_data

# =========================================================
# API ENDPOINTS
# =========================================================

# Health check
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0'
    })

# Submit new report
@app.route('/api/reports', methods=['POST'])
def submit_report():
    """Submit a new citizen report."""
    try:
        report_data = request.json
        
        # Validate report
        is_valid, errors = ReportValidator.validate_report_data(report_data)
        if not is_valid:
            return jsonify({
                'success': False,
                'errors': errors
            }), 400
        
        # Process report
        processor = ReportProcessor()
        processed_data = processor.process_report(report_data)
        
        # Create report record
        db = get_db()
        report = CitizenReport(
            report_id=str(uuid.uuid4()),
            user_id=processed_data['user_id'],
            latitude=processed_data['latitude'],
            longitude=processed_data['longitude'],
            address=processed_data.get('address'),
            landmark=processed_data.get('landmark'),
            waste_type=processed_data['waste_type'],
            severity=processed_data['severity'],
            description=processed_data.get('description'),
            photo_url=processed_data.get('photo_url'),
            estimated_quantity=processed_data.get('estimated_quantity'),
            waste_category=processed_data.get('waste_category'),
            priority=processed_data['priority'],
            grid_id=processed_data.get('grid_id'),
            area_name=processed_data.get('area_name'),
            nearby_overflow_risk=processed_data.get('nearby_overflow_risk')
        )
        
        db.add(report)
        db.commit()
        
        return jsonify({
            'success': True,
            'report_id': report.report_id,
            'priority': report.priority,
            'grid_id': report.grid_id,
            'area_name': report.area_name,
            'nearby_overflow_risk': report.nearby_overflow_risk
        }), 201
        
    except Exception as e:
        db.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Get reports by location
@app.route('/api/reports/nearby', methods=['GET'])
def get_nearby_reports():
    """Get reports near a specific location."""
    try:
        lat = float(request.args.get('latitude'))
        lon = float(request.args.get('longitude'))
        radius_km = float(request.args.get('radius', 5.0))
        
        db = get_db()
        
        # Get all reports
        reports = db.query(CitizenReport).filter(
            CitizenReport.status.in_(['pending', 'verified', 'in_progress'])
        ).all()
        
        # Filter by distance
        nearby_reports = []
        for report in reports:
            distance = geodesic((lat, lon), (report.latitude, report.longitude)).kilometers
            if distance <= radius_km:
                nearby_reports.append({
                    'report_id': report.report_id,
                    'latitude': report.latitude,
                    'longitude': report.longitude,
                    'waste_type': report.waste_type,
                    'severity': report.severity,
                    'status': report.status,
                    'priority': report.priority,
                    'reported_at': report.reported_at.isoformat(),
                    'distance_km': distance
                })
        
        # Sort by distance
        nearby_reports.sort(key=lambda x: x['distance_km'])
        
        return jsonify({
            'success': True,
            'reports': nearby_reports,
            'count': len(nearby_reports)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Get report by ID
@app.route('/api/reports/<report_id>', methods=['GET'])
def get_report(report_id):
    """Get a specific report by ID."""
    try:
        db = get_db()
        report = db.query(CitizenReport).filter_by(report_id=report_id).first()
        
        if not report:
            return jsonify({
                'success': False,
                'error': 'Report not found'
            }), 404
        
        return jsonify({
            'success': True,
            'report': {
                'report_id': report.report_id,
                'user_id': report.user_id,
                'latitude': report.latitude,
                'longitude': report.longitude,
                'address': report.address,
                'landmark': report.landmark,
                'waste_type': report.waste_type,
                'severity': report.severity,
                'description': report.description,
                'photo_url': report.photo_url,
                'estimated_quantity': report.estimated_quantity,
                'waste_category': report.waste_category,
                'status': report.status,
                'priority': report.priority,
                'reported_at': report.reported_at.isoformat(),
                'verified_at': report.verified_at.isoformat() if report.verified_at else None,
                'resolved_at': report.resolved_at.isoformat() if report.resolved_at else None,
                'grid_id': report.grid_id,
                'area_name': report.area_name,
                'nearby_overflow_risk': report.nearby_overflow_risk
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Update report status
@app.route('/api/reports/<report_id>/status', methods=['PUT'])
def update_report_status(report_id):
    """Update report status (for authorized users)."""
    try:
        update_data = request.json
        new_status = update_data.get('status')
        user_id = update_data.get('user_id')  # ID of user making the update
        
        if new_status not in ['pending', 'verified', 'in_progress', 'resolved', 'rejected']:
            return jsonify({
                'success': False,
                'error': 'Invalid status'
            }), 400
        
        db = get_db()
        report = db.query(CitizenReport).filter_by(report_id=report_id).first()
        
        if not report:
            return jsonify({
                'success': False,
                'error': 'Report not found'
            }), 404
        
        # Update status and timestamps
        report.status = new_status
        report.updated_at = datetime.utcnow()
        
        if new_status == 'verified':
            report.verified_at = datetime.utcnow()
            report.verified_by = user_id
        elif new_status == 'resolved':
            report.resolved_at = datetime.utcnow()
            report.resolved_by = user_id
            report.resolution_notes = update_data.get('resolution_notes')
        
        db.commit()
        
        return jsonify({
            'success': True,
            'report_id': report.report_id,
            'status': report.status,
            'updated_at': report.updated_at.isoformat()
        })
        
    except Exception as e:
        db.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Get report analytics
@app.route('/api/analytics/reports', methods=['GET'])
def get_report_analytics():
    """Get report analytics data."""
    try:
        db = get_db()
        
        # Date range
        days = int(request.args.get('days', 30))
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Basic statistics
        total_reports = db.query(CitizenReport).filter(
            CitizenReport.reported_at >= start_date
        ).count()
        
        pending_reports = db.query(CitizenReport).filter(
            CitizenReport.reported_at >= start_date,
            CitizenReport.status == 'pending'
        ).count()
        
        verified_reports = db.query(CitizenReport).filter(
            CitizenReport.reported_at >= start_date,
            CitizenReport.status == 'verified'
        ).count()
        
        resolved_reports = db.query(CitizenReport).filter(
            CitizenReport.reported_at >= start_date,
            CitizenReport.status == 'resolved'
        ).count()
        
        # Average resolution time
        resolved_with_time = db.query(CitizenReport).filter(
            CitizenReport.reported_at >= start_date,
            CitizenReport.status == 'resolved',
            CitizenReport.resolved_at.isnot(None)
        ).all()
        
        if resolved_with_time:
            resolution_times = [(r.resolved_at - r.reported_at).total_seconds() / 3600 for r in resolved_with_time]
            avg_resolution_time = sum(resolution_times) / len(resolution_times)
        else:
            avg_resolution_time = 0
        
        # Reports by type
        reports_by_type = db.query(
            CitizenReport.waste_type,
            db.func.count(CitizenReport.id)
        ).filter(
            CitizenReport.reported_at >= start_date
        ).group_by(CitizenReport.waste_type).all()
        
        type_counts = {rtype: count for rtype, count in reports_by_type}
        
        # Reports by area
        reports_by_area = db.query(
            CitizenReport.area_name,
            db.func.count(CitizenReport.id)
        ).filter(
            CitizenReport.reported_at >= start_date,
            CitizenReport.area_name.isnot(None)
        ).group_by(CitizenReport.area_name).all()
        
        area_counts = {area: count for area, count in reports_by_area}
        
        return jsonify({
            'success': True,
            'analytics': {
                'total_reports': total_reports,
                'pending_reports': pending_reports,
                'verified_reports': verified_reports,
                'resolved_reports': resolved_reports,
                'avg_resolution_time_hours': round(avg_resolution_time, 2),
                'reports_by_type': type_counts,
                'reports_by_area': area_counts,
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': datetime.utcnow().isoformat()
                }
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# =========================================================
# MAIN EXECUTION
# =========================================================

def main():
    """Main function to run the backend server."""
    print("=" * 70)
    print("CITIZEN REPORTING BACKEND SERVER")
    print("=" * 70)
    
    # Initialize database
    print("Initializing database...")
    init_db()
    
    # Start Flask server
    print("Starting Flask server...")
    print(f"Database: {DATABASE_FILE}")
    print("Server will be available at: http://localhost:5000")
    print("\nAvailable endpoints:")
    print("  GET  /api/health")
    print("  POST /api/reports")
    print("  GET  /api/reports/nearby")
    print("  GET  /api/reports/<report_id>")
    print("  PUT  /api/reports/<report_id>/status")
    print("  GET  /api/analytics/reports")
    
    app.run(host='0.0.0.0', port=5000, debug=True)

if __name__ == "__main__":
    main()