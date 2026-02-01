# Usa uma imagem Python leve e moderna
FROM python:3.10-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Variáveis de ambiente para otimizar o Python no Docker
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copia e instala as dependências primeiro (aproveita o cache do Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código do projeto para dentro do container
COPY . .

# Expõe a porta que o Flask/Gunicorn vai usar
EXPOSE 5000

# Comando para iniciar a aplicação usando Gunicorn (Produção)
# -w 4: Usa 4 workers (processos) para aguentar mais acessos simultâneos
# -b 0.0.0.0:5000: Libera o acesso externo na porta 5000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]