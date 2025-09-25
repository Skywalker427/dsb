import json
import re
import os
from typing import Dict, List, Optional, Any, Tuple
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.adapters.repos.clusters_repo import ClusterRepository
from app.adapters.repos.topics_repo import TopicRepository
from app.adapters.repos.suggestions_repo import SuggestionRepository
from app.adapters.repos.templates_repo import TemplateRepository
from app.domain.models import Cluster, Topic, Suggestion, Template, Document
from app.domain.enums import DocStatus


class DocumentGenerator:
    """Service for generating documents from clusters/topics using iterative LLM processing."""
    
    def __init__(self, db: AsyncSession, openai_client: Optional[AsyncOpenAI] = None):
        self.db = db
        self.openai_client = openai_client or AsyncOpenAI()
        self.clusters_repo = ClusterRepository(db)
        self.topics_repo = TopicRepository(db)
        self.suggestions_repo = SuggestionRepository(db)
        self.templates_repo = TemplateRepository(db)
        
        # Processing configuration from environment variables
        self.max_suggestions = int(os.getenv("DOC_GEN_MAX_SUGGESTIONS", "20"))
        self.suggestions_batch_size = int(os.getenv("DOC_GEN_BATCH_SIZE", "4"))
        self.max_iterations = max(50, (self.max_suggestions + self.suggestions_batch_size - 1) // self.suggestions_batch_size)  # Safety limit
    
    async def generate_document_from_cluster(
        self,
        cluster_id: UUID,
        template_id: UUID,
        document_title: Optional[str] = None,
        created_by: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Generate document from cluster suggestions using iterative LLM processing.
        Returns job payload data for background processing.
        """
        # Validate inputs
        cluster = await self.clusters_repo.get_by_id(cluster_id)
        if not cluster:
            raise ValueError(f"Cluster {cluster_id} not found")
        
        template = await self.templates_repo.get_by_id(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")
        
        # Get all suggestions in cluster
        suggestions = await self._get_cluster_suggestions(cluster_id)
        if not suggestions:
            raise ValueError(f"No suggestions found in cluster {cluster_id}")
        
        return {
            "source_type": "cluster",
            "source_id": str(cluster_id),
            "template_id": str(template_id),
            "document_title": document_title or f"Report for {cluster.title or 'Cluster'}",
            "created_by": str(created_by) if created_by else None,
            "total_suggestions": len(suggestions),
            "processing_status": "initialized",
        }
    
    async def generate_document_from_topic(
        self,
        topic_id: UUID,
        template_id: UUID,
        document_title: Optional[str] = None,
        created_by: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Generate document from topic suggestions using iterative LLM processing.
        Returns job payload data for background processing.
        """
        # Validate inputs
        topic = await self.topics_repo.get_by_id(topic_id)
        if not topic:
            raise ValueError(f"Topic {topic_id} not found")
        
        template = await self.templates_repo.get_by_id(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")
        
        # Get all suggestions for topic
        suggestions = await self._get_topic_suggestions(topic_id)
        if not suggestions:
            raise ValueError(f"No suggestions found for topic {topic_id}")
        
        return {
            "source_type": "topic",
            "source_id": str(topic_id),
            "template_id": str(template_id),
            "document_title": document_title or f"Report for {topic.label}",
            "created_by": str(created_by) if created_by else None,
            "total_suggestions": len(suggestions),
            "processing_status": "initialized",
        }
    
    async def process_document_generation_job(self, job_payload: Dict[str, Any]) -> Document:
        """
        Process document generation job with iterative LLM enhancement.
        This is called by the background job processor.
        """
        source_type = job_payload["source_type"]
        source_id = UUID(job_payload["source_id"])
        template_id = UUID(job_payload["template_id"])
        
        # Get template and source data
        template = await self.templates_repo.get_by_id(template_id)
        if source_type == "cluster":
            source = await self.clusters_repo.get_by_id(source_id)
            suggestions = await self._get_cluster_suggestions(source_id)
        else:  # topic
            source = await self.topics_repo.get_by_id(source_id)
            suggestions = await self._get_topic_suggestions(source_id)
        
        if not source or not template or not suggestions:
            raise ValueError("Invalid source, template, or no suggestions found")
        
        # Step 1: Create initial document with base context
        document_content = await self._create_initial_document(
            template, source, suggestions, source_type
        )
        
        # Step 2: Iteratively enhance with suggestion batches
        document_content = await self._enhance_document_iteratively(
            document_content, suggestions, source, source_type
        )
        
        # Step 3: Final refinement
        document_content = await self._finalize_document(
            document_content, suggestions, source, source_type
        )
        
        # Create the document record
        from app.adapters.repos.documents_repo import DocumentRepository
        docs_repo = DocumentRepository(self.db)
        
        document_data = {
            "title": job_payload["document_title"],
            "template_id": template_id,
            "status": DocStatus.READY,
            "draft_content": {
                "markdown": document_content,
                "source_type": source_type,
                "source_id": str(source_id),
                "template_info": {
                    "id": str(template_id),
                    "name": template.name,
                    "version": template.version,
                },
                "generation_stats": {
                    "total_suggestions": len(suggestions),
                    "suggestions_processed": len(suggestions),
                    "batches_processed": (len(suggestions) + self.suggestions_batch_size - 1) // self.suggestions_batch_size,
                }
            },
            "created_by": UUID(job_payload["created_by"]) if job_payload.get("created_by") else None,
        }
        
        document = await docs_repo.create(document_data)
        
        # Create relationships
        if source_type == "cluster":
            await docs_repo.add_cluster_association(document.id, source_id, 1.0)
        else:
            await docs_repo.add_topic_association(document.id, source_id, 1.0)
        
        return document
    
    async def _get_cluster_suggestions(self, cluster_id: UUID) -> List[Suggestion]:
        """Get suggestions in a cluster, ordered by similarity/confidence, limited by max_suggestions."""
        from app.domain.models import Suggestion, ClusterMember
        
        # Using SQLAlchemy ORM approach
        result = await self.db.execute(
            select(Suggestion)
            .join(ClusterMember, Suggestion.id == ClusterMember.suggestion_id)
            .where(ClusterMember.cluster_id == cluster_id)
            .order_by(ClusterMember.similarity.desc().nulls_last(), Suggestion.created_at.desc())
            .limit(self.max_suggestions)
        )
        return result.scalars().all()
    
    async def _get_topic_suggestions(self, topic_id: UUID) -> List[Suggestion]:
        """Get suggestions for a topic, ordered by confidence, limited by max_suggestions."""
        suggestions_with_confidence = await self.topics_repo.get_suggestions_by_topic(
            topic_id=topic_id,
            min_confidence=0.0,
            limit=self.max_suggestions
        )
        return [suggestion for suggestion, confidence in suggestions_with_confidence]
    
    async def _create_initial_document(
        self,
        template: Template,
        source: Any,
        suggestions: List[Suggestion],
        source_type: str,
    ) -> str:
        """Create initial document with basic context and metadata."""
        
        # Prepare source context
        if source_type == "cluster":
            source_context = f"""
            **Cluster Information:**
            - Title: {source.title or 'Untitled Cluster'}
            - Description: {source.description or 'No description'}
            - Type: {source.kind}
            - Tags: {', '.join(source.tags) if source.tags else 'None'}
            - Total Suggestions: {len(suggestions)}
            """
        else:  # topic
            source_context = f"""
            **Topic Information:**
            - Label: {source.label}
            - Description: {source.description or 'No description'}
            - Total Suggestions: {len(suggestions)}
            """
        
        # Basic statistics
        stats_context = self._generate_basic_stats(suggestions)
        
        system_prompt = f"""You are a document generator that creates comprehensive reports from customer suggestions. 

Your task is to take a template and fill it with relevant information from suggestion data. This is the INITIAL creation phase - you'll receive the template and basic context.

Rules:
1. Fill template placeholders ({{placeholder}}) with appropriate content
2. Use the provided source information and statistics
3. Create well-structured, professional content
4. Leave room for enhancement with specific suggestion details in later iterations
5. Focus on high-level insights and structure

Template Engine: {template.engine}
Source Type: {source_type}

Template Content:
{template.content_markdown}"""

        user_prompt = f"""Please generate the initial document content using this information:

{source_context}

{stats_context}

Template to fill: {template.name} (v{template.version})

Generate a professional document that fills the template placeholders with the provided information. Focus on structure and high-level insights - specific suggestion details will be added in subsequent iterations."""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=3000,
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            raise ValueError(f"Failed to create initial document: {str(e)}")
    
    async def _enhance_document_iteratively(
        self,
        document_content: str,
        suggestions: List[Suggestion],
        source: Any,
        source_type: str,
    ) -> str:
        """Enhance document iteratively with batches of suggestions."""
        
        current_content = document_content
        batches = [
            suggestions[i:i + self.suggestions_batch_size]
            for i in range(0, len(suggestions), self.suggestions_batch_size)
        ]
        
        for batch_index, suggestion_batch in enumerate(batches):
            if batch_index >= self.max_iterations:
                break
                
            batch_context = self._format_suggestion_batch(suggestion_batch)
            
            system_prompt = f"""You are enhancing a document by incorporating specific suggestion details.

Current Status: Processing batch {batch_index + 1} of {len(batches)}
You will receive the current document content and a batch of 1-3 suggestions.

Your task:
1. Review the current document content
2. Integrate insights, themes, and specific details from the suggestion batch
3. Enhance relevant sections without losing existing content
4. Add specific examples, quotes, or data points where appropriate
5. Maintain document structure and flow
6. Don't duplicate information already covered

Return the FULL enhanced document content."""

            user_prompt = f"""Current Document Content:
{current_content}

---

New Suggestion Batch to Integrate:
{batch_context}

Please enhance the document by thoughtfully integrating insights from these suggestions. Add specific details, examples, or themes that strengthen the existing content."""

            try:
                response = await self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=4000,
                )
                
                current_content = response.choices[0].message.content.strip()
                
            except Exception as e:
                # Log error but continue with current content
                print(f"Warning: Failed to enhance with batch {batch_index + 1}: {str(e)}")
                continue
        
        return current_content
    
    async def _finalize_document(
        self,
        document_content: str,
        suggestions: List[Suggestion],
        source: Any,
        source_type: str,
    ) -> str:
        """Final refinement pass on the document."""
        
        system_prompt = """You are performing the final refinement of a generated document.

Your task:
1. Review the entire document for consistency and flow
2. Ensure all sections are well-connected
3. Strengthen conclusions and recommendations based on the full analysis
4. Add executive summary elements if missing
5. Polish language and formatting
6. Ensure professional tone throughout
7. Add final statistics or insights that tie everything together

Return the FINAL polished document."""

        user_prompt = f"""Please perform final refinement on this document:

{document_content}

---

Total suggestions analyzed: {len(suggestions)}
Source type: {source_type}

Make this document publication-ready with strong conclusions and professional presentation."""

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,  # Lower temperature for final polish
                max_tokens=4000,
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            # Return current content if final polish fails
            print(f"Warning: Failed to finalize document: {str(e)}")
            return document_content
    
    def _generate_basic_stats(self, suggestions: List[Suggestion]) -> str:
        """Generate basic statistics from suggestions."""
        if not suggestions:
            return "**Statistics:** No suggestions available"
        
        # Count by author type
        staff_count = sum(1 for s in suggestions if s.author_type.value == "STAFF")
        customer_count = sum(1 for s in suggestions if s.author_type.value == "CUSTOMER")
        
        # Count by category
        category_counts = {}
        for suggestion in suggestions:
            cat = suggestion.category.value
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        # Count by status
        status_counts = {}
        for suggestion in suggestions:
            status = suggestion.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        stats = f"""
        **Statistics Summary:**
        - Total Suggestions: {len(suggestions)}
        - Staff Suggestions: {staff_count}
        - Customer Suggestions: {customer_count}
        - Categories: {', '.join([f'{k}: {v}' for k, v in category_counts.items()])}
        - Status: {', '.join([f'{k}: {v}' for k, v in status_counts.items()])}
        """
        
        return stats
    
    def _format_suggestion_batch(self, suggestions: List[Suggestion]) -> str:
        """Format a batch of suggestions for LLM processing."""
        formatted = []
        
        for i, suggestion in enumerate(suggestions, 1):
            formatted.append(f"""
            **Suggestion {i}:**
            - Title: {suggestion.title}
            - Category: {suggestion.category.value}
            - Author Type: {suggestion.author_type.value}
            - Content: {suggestion.body}
            - Tags: {', '.join(suggestion.tags) if suggestion.tags else 'None'}
            - Status: {suggestion.status.value}
            - Created: {suggestion.created_at.strftime('%Y-%m-%d')}
            """)
        
        return "\n".join(formatted)


# Factory function to create instance with database session
def get_document_generator(db: AsyncSession) -> DocumentGenerator:
    """Get document generator instance with database session."""
    return DocumentGenerator(db)