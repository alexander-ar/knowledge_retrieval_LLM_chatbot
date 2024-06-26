# Load packages
from openai import OpenAI
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
import os
import argparse
import tempfile

# fetch environmental variables
load_dotenv()

# helper function to process the input text file, remove empty lines and unneeded formatting marks
def process_input_text(input_file_path):
    '''
    process_input_text() helper function takes the text file as an argument and
    removes empty lines and non-essential characters. The output is saved
    in a temporary directory.
    
    Parameters:
        input_file_path (str): path to the input text file
    
    Returns:
        processed temporary text file path saved in temp/
    '''
    
    # create a temporary file in the same directory as input file
    temp_dir = os.path.join(os.path.dirname(input_file_path), "temp")
    os.makedirs(temp_dir, exist_ok = True)
    
    temp_file = tempfile.NamedTemporaryFile(mode = 'w', delete = False, dir = temp_dir, encoding = 'UTF-8')
    
    try:
        # Read the contents of the file
        with open(input_file_path, 'r', encoding = 'UTF-8') as input_file:
            lines = input_file.readlines()

        # Remove empty lines
        non_empty_lines = [line.strip() for line in lines if line.strip() and not all(char in {'-', '_'} for char in line.strip())]

        # write processed text to the temporary file
        temp_file.write('\n'.join(non_empty_lines))
    finally:
        # close the temporary file
        temp_file.close()
        
    # get the path of the temporary file
    temp_file_path = temp_file.name
    
    return temp_file_path


# helper function to ask questions to LLM chain
def answer_question(q, chain):
    '''
    answer_question() is a helper function to ask a single question from
    a LLM chain
    
    Parameters:
        q (str): user's question
        crc (langchain.chains.conversational_retrieval.base.ConversationalRetrievalChain):
            ConversationalRetrievalChain object from Langchain
    
    '''
    result = chain.invoke({'question': q})
    return result['answer']


# main app function
def main(input_text_file, input_question_file):
    '''
    main() function takes the text file with content and text file with
    questions as an arguments.  
    The input text file with questions may have several questions, 
    one question per line. Some of these questions may be follow up questions.
    Main() function prints out the answer to each 
    question in the corresponding order in the following format: 
    Answer to question 1: 
    The body of the answer.
    
    Parameters:
        input_text_file (str): path to the input text file with content
        input_question_file (str): path to the input text file with questions
    
    Returns:
        printed output with the GPT answer to each question
    '''
    # process input file
    processed_text_file_path = process_input_text(input_text_file)
    
    loader = TextLoader(processed_text_file_path, encoding = 'UTF-8') # need encoding specified
    data = loader.load() 
    
    # split the text using RecursiveCharacterTextSplitter
    text_splitter = RecursiveCharacterTextSplitter(chunk_size = 1024, chunk_overlap = 80)
    chunks = text_splitter.split_documents(data)
    
    # Instantiate an embedding model from AzureOpenAI
    embeddings = OpenAIEmbeddings(
        model='text-embedding-3-small', 
        dimensions=1536)  

    # Create an in-memory Chroma vector store using the provided text chunks 
    # and the embedding model 
    vector_store = Chroma.from_documents(documents = chunks, embedding = embeddings)
    
    # initialize the Azure LLM
    llm = ChatOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),  
        model = os.getenv("OPENAI_DEPLOYMENT_NAME"), 
        temperature=0)  

    # Configure vector store to act as a retriever (finding similar items, returning top 5)
    retriever = vector_store.as_retriever(search_type='similarity', search_kwargs={'k': 5})

    # Create a memory buffer to track the conversation
    memory = ConversationBufferMemory(memory_key='chat_history', return_messages=True)
    
    # build messages
    system_template = r'''
    You are answering questions only concerning the provided content of the input document.  
    If you are asked a question that is not related to the document you response will be:
    'The question is not relevant to the domain of interest'.
    ---------------
    Context: ```{context}```
    '''

    user_template = '''
    Answer questions only concerning the provided content of the input document.  
    If you are asked a question that is not related to the document you response will be:
    'The question is not relevant to the domain of interest'. 
    Here is the user's question: ```{question}```
    '''

    messages= [
        SystemMessagePromptTemplate.from_template(system_template),
        HumanMessagePromptTemplate.from_template(user_template)
        ]

    qa_prompt = ChatPromptTemplate.from_messages(messages)
    
    # Set up conversational retrieval chain
    crc = ConversationalRetrievalChain.from_llm(
        llm = llm,
        retriever = retriever,
        memory = memory,
        chain_type = 'stuff',
        combine_docs_chain_kwargs = {'prompt': qa_prompt },
        verbose = False)
    
    # process the input_question_file line by line
    with open(input_question_file, 'r') as file:
        question_counter = 0
        for line in file:
            question_counter += 1
            # Process each line
            new_user_question = line
            response = answer_question(q = new_user_question, chain = crc)
            print(f"Answering question {question_counter}: {new_user_question}")
            # print the response
            print(f"Answer to question {question_counter}: \n")
            print(response, "\n")


if __name__ == "__main__":
    # Set up command line argument parser
    parser = argparse.ArgumentParser(description = "Talk to your document chatbot application.")
    parser.add_argument("--content_text_file", help = "Input text file with content", required = True)
    parser.add_argument("--question_text_file", help = "Input text file with questions", required = True)

    # Parse command line arguments
    args = parser.parse_args()

    # Call the main function with the input file
    main(
        input_text_file = args.content_text_file, 
        input_question_file = args.question_text_file
        )