"""
Comprehensive spend tracking service for persona instances
"""

import asyncio
from typing import Dict, List, Any, Optional, Tuple
from uuid import UUID
from datetime import datetime, timedelta, date
from decimal import Decimal
import json

from backend.services.database import DatabaseManager
from backend.services.llm_provider_service import LLMProviderService
from backend.models.persona_instance import LLMModel


class SpendTrackingService:
    """Service for tracking and analyzing spend across persona instances"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.llm_service = LLMProviderService(db_manager)
    
    async def initialize(self):
        """Initialize the spend tracking service"""
        await self.llm_service.initialize()
    
    async def close(self):
        """Clean up resources"""
        await self.llm_service.close()
    
    async def record_llm_spend(
        self,
        instance_id: UUID,
        llm_model: LLMModel,
        input_tokens: int,
        output_tokens: int,
        task_description: str,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Record LLM usage and automatically calculate/update spend
        
        Returns dict with:
        - cost: Decimal cost of this operation
        - daily_limit_remaining: Decimal amount remaining today
        - monthly_limit_remaining: Decimal amount remaining this month
        - warnings: List of warning messages
        """
        # Calculate cost
        cost = self.llm_service.estimate_cost(llm_model, input_tokens, output_tokens)
        
        # Record in llm_usage_logs
        await self.llm_service.record_usage(
            instance_id=str(instance_id),
            llm_model=llm_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            success=success,
            error_message=error_message
        )
        
        # Update instance spend
        await self._update_instance_spend(instance_id, cost)
        
        # Get current limits
        limits = await self.get_spend_status(instance_id)
        
        warnings = []
        if limits['daily_percentage'] > 80:
            warnings.append(f"Daily spend at {limits['daily_percentage']:.1f}% of limit")
        if limits['monthly_percentage'] > 80:
            warnings.append(f"Monthly spend at {limits['monthly_percentage']:.1f}% of limit")
        
        # Record in spend_tracking table
        await self._record_spend_detail(
            instance_id=instance_id,
            amount=cost,
            category="llm_usage",
            description=task_description,
            metadata={
                "provider": llm_model.provider.value,
                "model": llm_model.model_name,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "success": success
            }
        )
        
        return {
            "cost": cost,
            "daily_limit_remaining": limits['daily_remaining'],
            "monthly_limit_remaining": limits['monthly_remaining'],
            "warnings": warnings
        }
    
    async def record_api_spend(
        self,
        instance_id: UUID,
        api_name: str,
        operation: str,
        cost: Decimal,
        request_count: int = 1
    ) -> Dict[str, Any]:
        """Record spend for API calls (Azure DevOps, etc.)"""
        await self._update_instance_spend(instance_id, cost)
        
        await self._record_spend_detail(
            instance_id=instance_id,
            amount=cost,
            category="api_usage",
            description=f"{api_name}: {operation}",
            metadata={
                "api": api_name,
                "operation": operation,
                "request_count": request_count
            }
        )
        
        limits = await self.get_spend_status(instance_id)
        return {
            "cost": cost,
            "daily_limit_remaining": limits['daily_remaining'],
            "monthly_limit_remaining": limits['monthly_remaining']
        }
    
    async def get_spend_status(self, instance_id: UUID) -> Dict[str, Any]:
        """Get current spend status for an instance"""
        query = """
        SELECT 
            current_spend_daily,
            current_spend_monthly,
            spend_limit_daily,
            spend_limit_monthly
        FROM orchestrator.persona_instances
        WHERE id = $1
        """
        
        result = await self.db.execute_query(query, instance_id, fetch_one=True)
        if not result:
            raise ValueError(f"Instance {instance_id} not found")
        
        return {
            "daily_spent": result['current_spend_daily'],
            "daily_limit": result['spend_limit_daily'],
            "daily_remaining": result['spend_limit_daily'] - result['current_spend_daily'],
            "daily_percentage": float(result['current_spend_daily'] / result['spend_limit_daily'] * 100),
            "monthly_spent": result['current_spend_monthly'],
            "monthly_limit": result['spend_limit_monthly'],
            "monthly_remaining": result['spend_limit_monthly'] - result['current_spend_monthly'],
            "monthly_percentage": float(result['current_spend_monthly'] / result['spend_limit_monthly'] * 100),
            "daily_exceeded": result['current_spend_daily'] >= result['spend_limit_daily'],
            "monthly_exceeded": result['current_spend_monthly'] >= result['spend_limit_monthly']
        }
    
    async def get_spend_history(
        self,
        instance_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get detailed spend history for an instance"""
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()
        
        query = """
        SELECT 
            id,
            amount,
            category,
            description,
            metadata,
            created_at
        FROM orchestrator.spend_tracking
        WHERE instance_id = $1
        AND created_at BETWEEN $2 AND $3
        """
        params = [instance_id, start_date, end_date]
        
        if category:
            query += " AND category = $4"
            params.append(category)
        
        query += " ORDER BY created_at DESC"
        
        results = await self.db.execute_query(query, *params)
        
        return [
            {
                "id": str(row['id']),
                "amount": row['amount'],
                "category": row['category'],
                "description": row['description'],
                "metadata": json.loads(row['metadata']) if row['metadata'] else {},
                "created_at": row['created_at'].isoformat()
            }
            for row in results
        ]
    
    async def get_spend_analytics(
        self,
        instance_id: Optional[UUID] = None,
        project: Optional[str] = None,
        persona_type_id: Optional[UUID] = None,
        time_period: str = "daily"  # daily, weekly, monthly
    ) -> Dict[str, Any]:
        """Get spend analytics with various filters"""
        # Build base query
        base_conditions = []
        params = []
        param_count = 0
        
        if instance_id:
            param_count += 1
            base_conditions.append(f"pi.id = ${param_count}")
            params.append(instance_id)
        
        if project:
            param_count += 1
            base_conditions.append(f"pi.azure_devops_project = ${param_count}")
            params.append(project)
        
        if persona_type_id:
            param_count += 1
            base_conditions.append(f"pi.persona_type_id = ${param_count}")
            params.append(persona_type_id)
        
        where_clause = " WHERE " + " AND ".join(base_conditions) if base_conditions else ""
        
        # Get aggregated data
        query = f"""
        SELECT 
            COUNT(DISTINCT pi.id) as instance_count,
            SUM(pi.current_spend_daily) as total_daily_spend,
            SUM(pi.current_spend_monthly) as total_monthly_spend,
            AVG(pi.current_spend_daily) as avg_daily_spend,
            AVG(pi.current_spend_monthly) as avg_monthly_spend,
            MAX(pi.current_spend_daily) as max_daily_spend,
            MAX(pi.current_spend_monthly) as max_monthly_spend,
            SUM(pi.spend_limit_daily) as total_daily_limit,
            SUM(pi.spend_limit_monthly) as total_monthly_limit
        FROM orchestrator.persona_instances pi
        {where_clause}
        """
        
        summary = await self.db.execute_query(query, *params, fetch_one=True)
        
        # Get spend by category
        category_query = f"""
        SELECT 
            st.category,
            COUNT(*) as transaction_count,
            SUM(st.amount) as total_amount,
            AVG(st.amount) as avg_amount
        FROM orchestrator.spend_tracking st
        JOIN orchestrator.persona_instances pi ON st.instance_id = pi.id
        {where_clause}
        GROUP BY st.category
        ORDER BY total_amount DESC
        """
        
        categories = await self.db.execute_query(category_query, *params)
        
        # Get top spenders
        top_spenders_query = f"""
        SELECT 
            pi.id,
            pi.instance_name,
            pi.current_spend_daily,
            pi.current_spend_monthly,
            pi.spend_limit_daily,
            pi.spend_limit_monthly,
            pt.display_name as persona_type
        FROM orchestrator.persona_instances pi
        LEFT JOIN orchestrator.persona_types pt ON pi.persona_type_id = pt.id
        {where_clause}
        ORDER BY pi.current_spend_monthly DESC
        LIMIT 10
        """
        
        top_spenders = await self.db.execute_query(top_spenders_query, *params)
        
        return {
            "summary": {
                "instance_count": summary['instance_count'],
                "total_daily_spend": float(summary['total_daily_spend'] or 0),
                "total_monthly_spend": float(summary['total_monthly_spend'] or 0),
                "avg_daily_spend": float(summary['avg_daily_spend'] or 0),
                "avg_monthly_spend": float(summary['avg_monthly_spend'] or 0),
                "max_daily_spend": float(summary['max_daily_spend'] or 0),
                "max_monthly_spend": float(summary['max_monthly_spend'] or 0),
                "daily_utilization": float(
                    (summary['total_daily_spend'] or 0) / (summary['total_daily_limit'] or 1) * 100
                ),
                "monthly_utilization": float(
                    (summary['total_monthly_spend'] or 0) / (summary['total_monthly_limit'] or 1) * 100
                )
            },
            "by_category": [
                {
                    "category": row['category'],
                    "transaction_count": row['transaction_count'],
                    "total_amount": float(row['total_amount']),
                    "avg_amount": float(row['avg_amount'])
                }
                for row in categories
            ],
            "top_spenders": [
                {
                    "id": str(row['id']),
                    "name": row['instance_name'],
                    "persona_type": row['persona_type'],
                    "daily_spend": float(row['current_spend_daily']),
                    "monthly_spend": float(row['current_spend_monthly']),
                    "daily_limit": float(row['spend_limit_daily']),
                    "monthly_limit": float(row['spend_limit_monthly']),
                    "daily_utilization": float(row['current_spend_daily'] / row['spend_limit_daily'] * 100),
                    "monthly_utilization": float(row['current_spend_monthly'] / row['spend_limit_monthly'] * 100)
                }
                for row in top_spenders
            ]
        }
    
    async def get_cost_projections(
        self,
        instance_id: UUID,
        days_ahead: int = 30
    ) -> Dict[str, Any]:
        """Project future costs based on historical data"""
        # Get last 30 days of data
        history = await self.get_spend_history(
            instance_id,
            start_date=datetime.utcnow() - timedelta(days=30)
        )
        
        if not history:
            return {
                "projected_daily_avg": 0,
                "projected_monthly_total": 0,
                "confidence": "low",
                "based_on_days": 0
            }
        
        # Calculate daily averages
        daily_totals = {}
        for record in history:
            date_key = datetime.fromisoformat(record['created_at']).date()
            if date_key not in daily_totals:
                daily_totals[date_key] = Decimal('0')
            daily_totals[date_key] += record['amount']
        
        # Calculate statistics
        daily_amounts = list(daily_totals.values())
        avg_daily = sum(daily_amounts) / len(daily_amounts) if daily_amounts else Decimal('0')
        
        # Project forward
        projected_monthly = avg_daily * 30
        
        # Determine confidence based on data points
        confidence = "high" if len(daily_totals) >= 20 else "medium" if len(daily_totals) >= 10 else "low"
        
        return {
            "projected_daily_avg": float(avg_daily),
            "projected_monthly_total": float(projected_monthly),
            "confidence": confidence,
            "based_on_days": len(daily_totals),
            "historical_daily_avg": float(avg_daily),
            "historical_daily_min": float(min(daily_amounts)) if daily_amounts else 0,
            "historical_daily_max": float(max(daily_amounts)) if daily_amounts else 0
        }
    
    async def set_spend_alerts(
        self,
        instance_id: UUID,
        daily_threshold_pct: int = 80,
        monthly_threshold_pct: int = 80
    ) -> None:
        """Set spend alert thresholds for an instance"""
        query = """
        INSERT INTO orchestrator.spend_alerts (
            instance_id,
            daily_threshold_pct,
            monthly_threshold_pct,
            created_at
        ) VALUES ($1, $2, $3, NOW())
        ON CONFLICT (instance_id) DO UPDATE SET
            daily_threshold_pct = $2,
            monthly_threshold_pct = $3,
            updated_at = NOW()
        """
        
        await self.db.execute_query(
            query,
            instance_id,
            daily_threshold_pct,
            monthly_threshold_pct
        )
    
    async def check_spend_alerts(self) -> List[Dict[str, Any]]:
        """Check all instances for spend alerts that should be triggered"""
        query = """
        SELECT 
            pi.id,
            pi.instance_name,
            pi.current_spend_daily,
            pi.current_spend_monthly,
            pi.spend_limit_daily,
            pi.spend_limit_monthly,
            sa.daily_threshold_pct,
            sa.monthly_threshold_pct,
            (pi.current_spend_daily / pi.spend_limit_daily * 100) as daily_pct,
            (pi.current_spend_monthly / pi.spend_limit_monthly * 100) as monthly_pct
        FROM orchestrator.persona_instances pi
        LEFT JOIN orchestrator.spend_alerts sa ON pi.id = sa.instance_id
        WHERE pi.is_active = true
        AND (
            (pi.current_spend_daily / pi.spend_limit_daily * 100) >= COALESCE(sa.daily_threshold_pct, 80)
            OR
            (pi.current_spend_monthly / pi.spend_limit_monthly * 100) >= COALESCE(sa.monthly_threshold_pct, 80)
        )
        """
        
        results = await self.db.execute_query(query)
        
        alerts = []
        for row in results:
            alert = {
                "instance_id": str(row['id']),
                "instance_name": row['instance_name'],
                "alerts": []
            }
            
            if row['daily_pct'] >= (row['daily_threshold_pct'] or 80):
                alert['alerts'].append({
                    "type": "daily_threshold",
                    "current_pct": float(row['daily_pct']),
                    "threshold_pct": row['daily_threshold_pct'] or 80,
                    "current_spend": float(row['current_spend_daily']),
                    "limit": float(row['spend_limit_daily'])
                })
            
            if row['monthly_pct'] >= (row['monthly_threshold_pct'] or 80):
                alert['alerts'].append({
                    "type": "monthly_threshold",
                    "current_pct": float(row['monthly_pct']),
                    "threshold_pct": row['monthly_threshold_pct'] or 80,
                    "current_spend": float(row['current_spend_monthly']),
                    "limit": float(row['spend_limit_monthly'])
                })
            
            if alert['alerts']:
                alerts.append(alert)
        
        return alerts
    
    async def optimize_spend_allocation(
        self,
        project: str,
        target_monthly_budget: Decimal
    ) -> Dict[str, Any]:
        """Suggest optimal spend allocation across instances in a project"""
        # Get all instances in project
        query = """
        SELECT 
            pi.id,
            pi.instance_name,
            pi.current_spend_monthly,
            pi.spend_limit_monthly,
            pt.display_name as persona_type,
            pt.category,
            COUNT(st.id) as transaction_count,
            AVG(st.amount) as avg_transaction_amount
        FROM orchestrator.persona_instances pi
        LEFT JOIN orchestrator.persona_types pt ON pi.persona_type_id = pt.id
        LEFT JOIN orchestrator.spend_tracking st ON pi.id = st.instance_id
        WHERE pi.azure_devops_project = $1
        AND pi.is_active = true
        GROUP BY pi.id, pi.instance_name, pi.current_spend_monthly, 
                 pi.spend_limit_monthly, pt.display_name
        """
        
        instances = await self.db.execute_query(query, project)
        
        if not instances:
            return {"error": "No active instances found in project"}
        
        # Calculate current total and suggested allocations
        current_total = sum(row['spend_limit_monthly'] for row in instances)
        
        # Priority weights by category
        category_weights = {
            "architecture": 1.5,
            "development": 1.2,
            "testing": 1.0,
            "operations": 1.1,
            "management": 0.9,
            "specialized": 1.3
        }
        
        # Calculate weighted scores
        weighted_instances = []
        total_weight = 0
        
        for instance in instances:
            weight = category_weights.get(instance['category'], 1.0)
            
            # Default weight if category not available
            weight = 1.0
            
            # Adjust weight based on usage
            if instance['current_spend_monthly'] and instance['spend_limit_monthly']:
                usage_ratio = float(instance['current_spend_monthly'] / instance['spend_limit_monthly'])
                if usage_ratio > 0.9:  # High usage
                    weight *= 1.2
                elif usage_ratio < 0.3:  # Low usage
                    weight *= 0.8
            
            weighted_instances.append({
                "instance": instance,
                "weight": weight
            })
            total_weight += weight
        
        # Calculate new allocations
        recommendations = []
        total_allocated = Decimal('0')
        
        for wi in weighted_instances:
            instance = wi['instance']
            allocation_pct = wi['weight'] / total_weight
            suggested_limit = target_monthly_budget * Decimal(str(allocation_pct))
            
            # Round to nearest $5
            suggested_limit = Decimal(int(suggested_limit / 5) * 5)
            
            # Ensure minimum allocation
            suggested_limit = max(suggested_limit, Decimal('25.00'))
            
            total_allocated += suggested_limit
            
            recommendations.append({
                "instance_id": str(instance['id']),
                "instance_name": instance['instance_name'],
                "persona_type": instance.get('persona_type', 'Unknown'),
                "current_limit": float(instance['spend_limit_monthly']),
                "current_spend": float(instance['current_spend_monthly']),
                "suggested_limit": float(suggested_limit),
                "change_pct": float((suggested_limit - instance['spend_limit_monthly']) / instance['spend_limit_monthly'] * 100),
                "allocation_reason": self._get_allocation_reason(
                    instance,
                    wi['weight'],
                    allocation_pct
                )
            })
        
        # Sort by suggested change
        recommendations.sort(key=lambda x: abs(x['change_pct']), reverse=True)
        
        return {
            "project": project,
            "target_budget": float(target_monthly_budget),
            "current_total_limit": float(current_total),
            "suggested_total": float(total_allocated),
            "instance_count": len(instances),
            "recommendations": recommendations
        }
    
    def _get_allocation_reason(
        self,
        instance: Dict[str, Any],
        weight: float,
        allocation_pct: float
    ) -> str:
        """Generate human-readable reason for allocation"""
        reasons = []
        
        if weight > 1.3:
            reasons.append("High priority role")
        
        if instance['current_spend_monthly'] and instance['spend_limit_monthly']:
            usage_ratio = float(instance['current_spend_monthly'] / instance['spend_limit_monthly'])
            if usage_ratio > 0.9:
                reasons.append("Currently at capacity")
            elif usage_ratio < 0.3:
                reasons.append("Low utilization")
        
        if allocation_pct > 0.2:
            reasons.append("Major contributor to project")
        elif allocation_pct < 0.05:
            reasons.append("Minor role in project")
        
        return "; ".join(reasons) if reasons else "Standard allocation"
    
    async def _update_instance_spend(
        self,
        instance_id: UUID,
        amount: Decimal
    ) -> None:
        """Update instance spend totals"""
        query = """
        UPDATE orchestrator.persona_instances
        SET 
            current_spend_daily = current_spend_daily + $2,
            current_spend_monthly = current_spend_monthly + $2
        WHERE id = $1
        """
        
        await self.db.execute_query(query, instance_id, amount)
    
    async def _record_spend_detail(
        self,
        instance_id: UUID,
        amount: Decimal,
        category: str,
        description: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record detailed spend tracking entry"""
        query = """
        INSERT INTO orchestrator.spend_tracking (
            instance_id,
            amount,
            category,
            description,
            metadata,
            created_at
        ) VALUES ($1, $2, $3, $4, $5, NOW())
        """
        
        await self.db.execute_query(
            query,
            instance_id,
            amount,
            category,
            description,
            json.dumps(metadata) if metadata else None
        )