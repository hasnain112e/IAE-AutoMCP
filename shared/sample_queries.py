"""
Diverse Sample Query Generator

Generates semantically unique and diverse sample queries for the Chat API.
Ensures no repetition and covers various query types.
"""

import random
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class QueryType(Enum):
    """Types of queries to generate."""
    INFORMATIONAL = "informational"  # "What is...", "How does..."
    ACTION = "action"  # "Create...", "Delete...", "Update..."
    CALCULATION = "calculation"  # "Calculate...", "Compute..."
    SEARCH = "search"  # "Find...", "Search for..."
    LIST = "list"  # "List all...", "Show..."
    STATUS = "status"  # "Get status...", "Check..."
    COMPARISON = "comparison"  # "Compare...", "Difference between..."
    AGGREGATION = "aggregation"  # "Total...", "Count...", "Sum..."


@dataclass
class SampleQuery:
    """A sample query with metadata."""
    query: str
    query_type: QueryType
    description: str
    expected_tools: List[str]  # Tool names this query might use
    complexity: str  # "simple", "medium", "complex"


# Pre-defined diverse query templates by type
QUERY_TEMPLATES = {
    QueryType.INFORMATIONAL: [
        "What is the current {entity} for {target}?",
        "How does {feature} work in {context}?",
        "Explain the {concept} in {domain}",
        "What are the details of {item} with ID {id}?",
        "Describe the {attribute} of {entity}",
    ],
    QueryType.ACTION: [
        "Create a new {entity} with name '{name}'",
        "Update the {attribute} of {entity} to '{value}'",
        "Delete the {entity} with ID {id}",
        "Add {item} to the {collection}",
        "Remove {item} from {entity}",
    ],
    QueryType.CALCULATION: [
        "Calculate the total {metric} for {entity}",
        "Compute the average {attribute} across all {entities}",
        "What is the sum of {values} for {period}?",
        "Determine the percentage of {category} in {total}",
        "Find the maximum {metric} in {dataset}",
    ],
    QueryType.SEARCH: [
        "Find all {entities} matching '{criteria}'",
        "Search for {entity} with {attribute} containing '{term}'",
        "Locate {items} where {condition}",
        "Look up {entity} by {identifier}",
        "Query {source} for {pattern}",
    ],
    QueryType.LIST: [
        "List all {entities} in the system",
        "Show the top {count} {entities} by {metric}",
        "Get all {items} created after {date}",
        "Display {entities} sorted by {attribute}",
        "Enumerate {collection} with status '{status}'",
    ],
    QueryType.STATUS: [
        "Get the current status of {entity}",
        "Check if {entity} is {state}",
        "What is the health status of {service}?",
        "Is {entity} available for {action}?",
        "Report on {system} performance",
    ],
    QueryType.COMPARISON: [
        "Compare {entity1} with {entity2}",
        "What's the difference between {a} and {b}?",
        "Contrast {feature1} and {feature2} in {context}",
        "Which is better: {option1} or {option2}?",
        "Analyze {entity} versus {baseline}",
    ],
    QueryType.AGGREGATION: [
        "Count all {entities} in {category}",
        "Total revenue from {source} this {period}",
        "Sum of {values} grouped by {dimension}",
        "Average {metric} per {unit}",
        "Statistics for {dataset} in {timeframe}",
    ],
}


# Sample data for template filling
SAMPLE_DATA = {
    "entity": ["user", "order", "product", "account", "transaction", "post", "comment", "file"],
    "entities": ["users", "orders", "products", "accounts", "transactions", "posts", "comments", "files"],
    "target": ["user123", "order456", "product789", "account001", "customer-xyz"],
    "feature": ["authentication", "caching", "pagination", "filtering", "sorting"],
    "context": ["API v2", "production", "staging", "the dashboard", "mobile app"],
    "concept": ["rate limiting", "OAuth flow", "webhook", "batch processing", "async tasks"],
    "domain": ["e-commerce", "finance", "social media", "healthcare", "logistics"],
    "item": ["item", "record", "entry", "document", "resource"],
    "attribute": ["name", "email", "status", "price", "quantity", "description"],
    "value": ["active", "premium", "verified", "pending", "completed"],
    "name": ["New Project", "Test Item", "Sample Record", "My Document", "API Config"],
    "id": ["123", "456", "789", "abc-123", "uuid-xyz"],
    "collection": ["cart", "wishlist", "favorites", "history", "queue"],
    "metric": ["sales", "views", "clicks", "conversions", "revenue"],
    "values": ["prices", "quantities", "scores", "ratings", "amounts"],
    "period": ["today", "this week", "last month", "Q4 2024", "year-to-date"],
    "category": ["electronics", "premium", "new arrivals", "on sale", "featured"],
    "total": ["inventory", "catalog", "database", "system"],
    "criteria": ["active users", "pending orders", "low stock", "high priority"],
    "term": ["John", "test", "demo", "sample", "urgent"],
    "condition": ["status = active", "price > 100", "created today", "updated recently"],
    "identifier": ["ID", "email", "username", "SKU", "reference"],
    "source": ["database", "API", "cache", "external service", "file system"],
    "pattern": ["error logs", "user activity", "sales data", "metrics"],
    "count": ["10", "5", "20", "50", "100"],
    "date": ["2024-01-01", "yesterday", "last week", "30 days ago"],
    "status": ["active", "pending", "completed", "failed", "processing"],
    "state": ["online", "available", "ready", "processing", "idle"],
    "service": ["API gateway", "database", "cache server", "queue", "worker"],
    "action": ["processing", "shipping", "refund", "update", "deletion"],
    "system": ["overall", "payment", "notification", "analytics", "reporting"],
    "entity1": ["plan A", "version 1", "option X", "product A", "method 1"],
    "entity2": ["plan B", "version 2", "option Y", "product B", "method 2"],
    "a": ["REST", "synchronous", "SQL", "monolith", "HTTP"],
    "b": ["GraphQL", "asynchronous", "NoSQL", "microservices", "WebSocket"],
    "feature1": ["performance", "security", "scalability", "usability"],
    "feature2": ["cost", "reliability", "flexibility", "simplicity"],
    "option1": ["caching", "indexing", "pagination", "batching"],
    "option2": ["lazy loading", "streaming", "chunking", "compression"],
    "baseline": ["last month", "industry average", "competitor", "previous version"],
    "dimension": ["region", "product", "customer", "channel", "time"],
    "unit": ["user", "day", "transaction", "request", "session"],
    "dataset": ["sales", "traffic", "errors", "performance", "usage"],
    "timeframe": ["real-time", "hourly", "daily", "weekly", "monthly"],
}


class DiverseQueryGenerator:
    """
    Generates diverse, semantically unique sample queries.
    
    Ensures:
    - No repetition of queries
    - Coverage of all query types
    - Varied complexity levels
    - Realistic scenarios
    """
    
    def __init__(self, tools: Optional[List[Dict[str, Any]]] = None):
        self.tools = tools or []
        self.used_queries: set = set()
        self.type_counter: Dict[QueryType, int] = {t: 0 for t in QueryType}
    
    def generate_query(self, query_type: Optional[QueryType] = None) -> SampleQuery:
        """
        Generate a single diverse query.
        
        Args:
            query_type: Optional specific query type, or None for balanced selection
            
        Returns:
            SampleQuery with unique query text
        """
        # Select query type (balanced selection if not specified)
        if query_type is None:
            # Pick the least-used type for balance
            query_type = min(self.type_counter, key=lambda t: self.type_counter[t])
        
        # Get templates for this type
        templates = QUERY_TEMPLATES.get(query_type, QUERY_TEMPLATES[QueryType.INFORMATIONAL])
        
        # Try to generate a unique query
        max_attempts = 20
        for _ in range(max_attempts):
            template = random.choice(templates)
            filled = self._fill_template(template)
            
            if filled not in self.used_queries:
                self.used_queries.add(filled)
                self.type_counter[query_type] += 1
                
                return SampleQuery(
                    query=filled,
                    query_type=query_type,
                    description=f"Sample {query_type.value} query",
                    expected_tools=self._match_tools(filled),
                    complexity=self._assess_complexity(filled)
                )
        
        # Fallback: generate with timestamp to ensure uniqueness
        fallback = f"{random.choice(templates)} (variant {len(self.used_queries)})"
        filled = self._fill_template(fallback)
        self.used_queries.add(filled)
        
        return SampleQuery(
            query=filled,
            query_type=query_type,
            description=f"Sample {query_type.value} query",
            expected_tools=[],
            complexity="simple"
        )
    
    def generate_queries(self, count: int = 10) -> List[SampleQuery]:
        """
        Generate multiple diverse queries.
        
        Args:
            count: Number of queries to generate
            
        Returns:
            List of unique SampleQuery objects
        """
        queries = []
        
        # Ensure coverage of all query types first
        for qt in QueryType:
            if len(queries) >= count:
                break
            queries.append(self.generate_query(qt))
        
        # Fill remaining with balanced selection
        while len(queries) < count:
            queries.append(self.generate_query())
        
        return queries
    
    def generate_for_tools(self, tool_names: List[str]) -> List[SampleQuery]:
        """
        Generate queries tailored to specific tools.
        
        Args:
            tool_names: List of tool names to generate queries for
            
        Returns:
            List of queries relevant to the provided tools
        """
        queries = []
        
        for tool_name in tool_names[:10]:  # Limit to 10 tools
            # Infer query type from tool name
            query_type = self._infer_query_type_from_tool(tool_name)
            query = self.generate_query(query_type)
            
            # Customize query to mention the tool
            customized = self._customize_for_tool(query.query, tool_name)
            
            queries.append(SampleQuery(
                query=customized,
                query_type=query_type,
                description=f"Query for {tool_name}",
                expected_tools=[tool_name],
                complexity=query.complexity
            ))
        
        return queries
    
    def _fill_template(self, template: str) -> str:
        """Fill template placeholders with random data."""
        result = template
        
        for key, values in SAMPLE_DATA.items():
            placeholder = "{" + key + "}"
            while placeholder in result:
                result = result.replace(placeholder, random.choice(values), 1)
        
        return result
    
    def _match_tools(self, query: str) -> List[str]:
        """Match query to relevant tools."""
        if not self.tools:
            return []
        
        query_lower = query.lower()
        matched = []
        
        for tool in self.tools:
            tool_name = tool.get("name", "").lower()
            tool_desc = tool.get("description", "").lower()
            
            # Simple keyword matching
            if any(word in query_lower for word in tool_name.split("_")):
                matched.append(tool.get("name", ""))
            elif any(word in tool_desc for word in query_lower.split()):
                matched.append(tool.get("name", ""))
        
        return matched[:3]  # Return top 3 matches
    
    def _assess_complexity(self, query: str) -> str:
        """Assess query complexity."""
        word_count = len(query.split())
        
        if word_count <= 5:
            return "simple"
        elif word_count <= 12:
            return "medium"
        else:
            return "complex"
    
    def _infer_query_type_from_tool(self, tool_name: str) -> QueryType:
        """Infer appropriate query type from tool name."""
        name_lower = tool_name.lower()
        
        if any(w in name_lower for w in ["get", "fetch", "read", "show"]):
            return QueryType.INFORMATIONAL
        elif any(w in name_lower for w in ["create", "add", "post", "insert"]):
            return QueryType.ACTION
        elif any(w in name_lower for w in ["update", "put", "patch", "modify"]):
            return QueryType.ACTION
        elif any(w in name_lower for w in ["delete", "remove", "clear"]):
            return QueryType.ACTION
        elif any(w in name_lower for w in ["list", "all", "index"]):
            return QueryType.LIST
        elif any(w in name_lower for w in ["search", "find", "query"]):
            return QueryType.SEARCH
        elif any(w in name_lower for w in ["count", "sum", "total", "stats"]):
            return QueryType.AGGREGATION
        elif any(w in name_lower for w in ["status", "health", "check"]):
            return QueryType.STATUS
        else:
            return random.choice(list(QueryType))
    
    def _customize_for_tool(self, query: str, tool_name: str) -> str:
        """Customize query to be more relevant to a specific tool."""
        # Convert tool name to readable format
        readable = tool_name.replace("_", " ").replace("-", " ")
        
        # Simple customization based on tool name patterns
        if "get" in tool_name.lower():
            return f"Using {readable}: {query}"
        elif "create" in tool_name.lower() or "add" in tool_name.lower():
            return f"I want to {readable.lower()}"
        elif "delete" in tool_name.lower():
            return f"Please {readable.lower()} for the item"
        elif "list" in tool_name.lower():
            return f"Show me the results from {readable.lower()}"
        else:
            return query


def get_sample_queries(count: int = 5, tools: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    """
    Convenience function to get diverse sample queries.
    
    Args:
        count: Number of queries to generate
        tools: Optional list of tools to tailor queries
        
    Returns:
        List of query strings
    """
    generator = DiverseQueryGenerator(tools)
    queries = generator.generate_queries(count)
    return [q.query for q in queries]


def get_sample_queries_with_metadata(
    count: int = 5,
    tools: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Get diverse sample queries with full metadata.
    
    Args:
        count: Number of queries to generate
        tools: Optional list of tools to tailor queries
        
    Returns:
        List of query dictionaries with metadata
    """
    generator = DiverseQueryGenerator(tools)
    queries = generator.generate_queries(count)
    
    return [
        {
            "query": q.query,
            "type": q.query_type.value,
            "description": q.description,
            "expected_tools": q.expected_tools,
            "complexity": q.complexity
        }
        for q in queries
    ]


# Pre-generated static examples for immediate use
STATIC_DIVERSE_EXAMPLES = [
    "What is the current status for user123?",
    "Create a new product with name 'Premium Widget'",
    "Calculate the total revenue for this month",
    "Find all orders matching 'pending shipment'",
    "List all users in the system sorted by creation date",
    "Get the health status of the API gateway",
    "Compare version 1 with version 2 performance",
    "Count all transactions grouped by category",
    "Update the email of account abc-123 to 'new@example.com'",
    "Search for products with description containing 'wireless'",
]

