import random
from typing import List, Dict, Any

import dspy
from django.conf import settings
from openai import OpenAI

from .search import ManPageSearch


class ManPageRAGService:
    """RAG service for answering questions using man-page documentation."""
    
    def __init__(self):
        self.searcher = ManPageSearch()
        
        # Check if OpenAI API key is configured
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not configured in settings. Please set it in your environment variables.")
        
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._setup_dspy()
    
    def _setup_dspy(self):
        """Setup DSPy with OpenAI model."""
        try:
            # Try the newer DSPy API first
            lm = dspy.LM(f'openai/{settings.OPENAI_MODEL}')
            dspy.configure(lm=lm)
        except AttributeError:
            # Fallback to older API if available
            try:
                lm = dspy.OpenAI(
                    model=settings.OPENAI_MODEL,
                    api_key=settings.OPENAI_API_KEY,
                    max_tokens=1000,
                    temperature=0.1
                )
                dspy.settings.configure(lm=lm)
            except AttributeError:
                # If DSPy is not properly installed or configured, we'll use fallback
                print("Warning: DSPy not properly configured, using fallback OpenAI API")
    
    def search_relevant_chunks(self, question: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for relevant chunks based on the question.
        
        Args:
            question (str): The user's question
            limit (int): Maximum number of chunks to retrieve
        
        Returns:
            List[Dict]: Relevant chunks with metadata
        """
        chunks = self.searcher.search_chunks(
            query=question,
            search_type='vector',
            limit=limit,
            score_threshold=0.6
        )
        
        results = []
        for chunk in chunks:
            results.append({
                'id': str(chunk.id),
                'document_name': chunk.document.name,
                'document_section': chunk.document.section,
                'document_title': chunk.document.title,
                'section_name': chunk.section_name,
                'anchor': chunk.anchor,
                'text': chunk.text,
                'similarity': getattr(chunk, 'similarity', None),
            })
        
        return results
    
    def generate_answer(self, question: str, context_chunks: List[Dict[str, Any]]) -> str:
        """
        Generate an answer using DSPy based on the question and context.
        
        Args:
            question (str): The user's question
            context_chunks (List[Dict]): Relevant chunks from search
        
        Returns:
            str: Generated answer
        """
        # Prepare context from chunks
        context_text = self._prepare_context(context_chunks)
        
        # Try DSPy first
        try:
            # Create DSPy signature for Q&A
            class ManPageQA(dspy.Signature):
                """Answer questions about Linux man pages based on provided context."""
                context = dspy.InputField(desc="Relevant man page documentation")
                question = dspy.InputField(desc="User's question about Linux commands or system functions")
                answer = dspy.OutputField(desc="Comprehensive answer based on the context")
            
            # Create the module
            qa_module = dspy.ChainOfThought(ManPageQA)
            
            # Generate answer
            result = qa_module(context=context_text, question=question)
            return result.answer
        except Exception as e:
            # Fallback to simple prompt if DSPy fails
            print(f"DSPy failed, using fallback: {str(e)}")
            return self._fallback_answer(question, context_text)
    
    def _prepare_context(self, chunks: List[Dict[str, Any]]) -> str:
        """Prepare context text from chunks."""
        context_parts = []
        
        for i, chunk in enumerate(chunks, 1):
            doc_info = f"Document: {chunk['document_name']}({chunk['document_section']}) - {chunk['document_title']}"
            section_info = f"Section: {chunk['section_name']}"
            text_content = chunk['text']
            
            context_parts.append(f"[{i}] {doc_info}\n{section_info}\n{text_content}\n")
        
        return "\n".join(context_parts)
    
    def _fallback_answer(self, question: str, context: str) -> str:
        """Fallback answer generation using direct OpenAI API."""
        prompt = f"""You are a helpful assistant that answers questions about Linux man pages. 
Use the provided context from man page documentation to answer the user's question accurately and comprehensively.

Context from man pages:
{context}

Question: {question}

Please provide a detailed answer based on the context above. If the context doesn't contain enough information to answer the question, say so clearly."""

        try:
            response = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a Linux documentation expert."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.1
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"I apologize, but I encountered an error while generating an answer: {str(e)}"
    
    def ask_question(self, question: str) -> Dict[str, Any]:
        """
        Main method to ask a question and get an answer with context.
        
        Args:
            question (str): The user's question
        
        Returns:
            Dict: Answer with metadata
        """
        # Search for relevant chunks
        relevant_chunks = self.search_relevant_chunks(question)
        
        if not relevant_chunks:
            return {
                'answer': "I couldn't find any relevant information in the man pages to answer your question.",
                'context_chunks': [],
                'sources': [],
                'question': question
            }
        
        # Generate answer using DSPy
        answer = self.generate_answer(question, relevant_chunks)
        
        # Prepare sources
        sources = []
        for chunk in relevant_chunks:
            sources.append({
                'document': f"{chunk['document_name']}({chunk['document_section']})",
                'title': chunk['document_title'],
                'section': chunk['section_name'],
                'similarity': chunk['similarity']
            })
        
        return {
            'answer': answer,
            'context_chunks': relevant_chunks,
            'sources': sources,
            'question': question
        }
    
    def get_random_loading_message(self) -> str:
        """Get a random funny loading message."""
        return random.choice(settings.FUNNY_LOADING_SENTENCES)
