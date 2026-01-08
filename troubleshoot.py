from langchain_ollama import OllamaEmbeddings

# Kiểm tra xem Ollama trả về bao nhiêu
embeddings = OllamaEmbeddings(model="nomic-embed-text")
test_vec = embeddings.embed_query("test query")
print(f"Thực tế Model trả về dimension: {len(test_vec)}")