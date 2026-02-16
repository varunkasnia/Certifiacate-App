"""RAG Pipeline for quiz generation using OpenAI API"""
import os
import json
import re
from django.conf import settings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import PromptTemplate

class RAGPipeline:
    """RAG pipeline for generating quiz questions using OpenAI"""

    def __init__(self):
        api_key = settings.OPENAI_API_KEY
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Add it to your .env file. "
                "Get your key from https://platform.openai.com/api-keys"
            )
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=api_key,
            model=settings.OPENAI_EMBEDDING_MODEL
        )
        self.llm = ChatOpenAI(
            openai_api_key=api_key,
            model=settings.OPENAI_MODEL,
            temperature=0.7
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP
        )
        self.vector_store = None

    def create_vector_store(self, texts, quiz_id):
        """Create vector store from texts"""
        chunks = self.text_splitter.create_documents(texts)
        vector_store_path = os.path.join(settings.VECTOR_DB_PATH, str(quiz_id))
        os.makedirs(vector_store_path, exist_ok=True)
        
        self.vector_store = FAISS.from_documents(chunks, self.embeddings)
        self.vector_store.save_local(vector_store_path)
        return self.vector_store

    def load_vector_store(self, quiz_id):
        """Load existing vector store"""
        vector_store_path = os.path.join(settings.VECTOR_DB_PATH, str(quiz_id))
        if os.path.exists(vector_store_path):
            self.vector_store = FAISS.load_local(
                vector_store_path,
                self.embeddings,
                allow_dangerous_deserialization=True
            )
        return self.vector_store

    def retrieve_context(self, query, k=3):
        """Retrieve relevant context from vector store"""
        if not self.vector_store:
            return ""
        
        docs = self.vector_store.similarity_search(query, k=k)
        context = "\n\n".join([doc.page_content for doc in docs])
        return context

    def generate_questions(self, num_questions, difficulty, context=None):
        """Generate MCQ questions using LLM"""
        if not context:
            context = "General knowledge"

        prompt_template = PromptTemplate(
            input_variables=["context", "num_questions", "difficulty"],
            template="""
You are an expert quiz creator. Generate {num_questions} multiple-choice questions based on the following context.

Context:
{context}

Difficulty Level: {difficulty}

Requirements:
1. Each question must have exactly 4 options (A, B, C, D)
2. Only one correct answer per question
3. Questions should be clear and unambiguous
4. Options should be plausible distractors
5. Include a brief explanation for each correct answer

Output format (JSON):
{{
  "questions": [
    {{
      "question": "Question text here",
      "options": {{
        "A": "Option A text",
        "B": "Option B text",
        "C": "Option C text",
        "D": "Option D text"
      }},
      "correct_answer": "A",
      "explanation": "Brief explanation"
    }}
  ]
}}

Generate exactly {num_questions} questions. Return only valid JSON, no markdown formatting.
"""
        )

        # Updated: Use LCEL pipe syntax instead of LLMChain
        chain = prompt_template | self.llm
        
        # Generate questions in batches if needed
        all_questions = []
        batch_size = min(5, num_questions)
        
        for i in range(0, num_questions, batch_size):
            current_batch = min(batch_size, num_questions - i)
            
            # Updated: use invoke() with dictionary input
            result = chain.invoke({
                "context": context[:2000],
                "num_questions": current_batch,
                "difficulty": difficulty
            })
            
            # Handle AIMessage or string response
            if hasattr(result, 'content'):
                result = result.content
            result = str(result)
            
            try:
                # Clean JSON response
                result = result.strip()
                if result.startswith("```json"):
                    result = result[7:]
                if result.startswith("```"):
                    result = result[3:]
                if result.endswith("```"):
                    result = result[:-3]
                result = result.strip()
                
                data = json.loads(result)
                all_questions.extend(data.get("questions", []))
            except json.JSONDecodeError:
                # Fallback: try to extract JSON from text
                json_match = re.search(r'\{.*\}', result, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group())
                        all_questions.extend(data.get("questions", []))
                    except:
                        pass

        return all_questions[:num_questions]