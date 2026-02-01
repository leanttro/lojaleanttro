from flask import Flask, render_template, request, jsonify
import requests
import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente (Dokploy/Contabo injetam isso)
load_dotenv()

app = Flask(__name__)

# --- CONFIGURAÇÕES DO AMBIENTE ---
# Se não tiver ENV definido, usa valores vazios para não quebrar no start, mas vai dar erro na requisição
DIRECTUS_URL = os.getenv("DIRECTUS_URL", "https://api2.leanttro.com")
DIRECTUS_TOKEN = os.getenv("DIRECTUS_TOKEN", "") 
MELHOR_ENVIO_TOKEN = os.getenv("MELHOR_ENVIO_TOKEN", "")
LOJA_ID = os.getenv("LOJA_ID", "") 

# --- TABELA DE MEDIDAS (TRADUÇÃO DA "CLASSE DE FRETE") ---
# Mapeia o Dropdown do Directus para pesos/medidas reais do Melhor Envio
DIMENSOES = {
    "Pequeno": {"height": 4, "width": 12, "length": 16, "weight": 0.3}, # Envelope/Caixa P (Kits Bijus)
    "Medio":   {"height": 10, "width": 20, "length": 20, "weight": 1.0}, # Kits maiores (Garrafas/Kits Misto)
    "Grande":  {"height": 20, "width": 30, "length": 30, "weight": 3.0}  # Caixas grandes
}

@app.route('/')
def index():
    # Headers para autenticação no Directus (se necessário)
    headers = {"Authorization": f"Bearer {DIRECTUS_TOKEN}"} if DIRECTUS_TOKEN else {}
    
    # 1. Busca Dados da Loja (Configurações, Logo, Cores)
    try:
        # Tenta buscar pelo ID específico da loja
        if LOJA_ID:
            resp_loja = requests.get(f"{DIRECTUS_URL}/items/lojas/{LOJA_ID}", headers=headers)
            if resp_loja.status_code == 200:
                loja = resp_loja.json().get('data', {})
            else:
                loja = {"nome": "Minha Loja", "cor_primaria": "#dc2626"} # Fallback
        else:
            loja = {"nome": "Configure o LOJA_ID", "cor_primaria": "#dc2626"}
    except Exception as e:
        print(f"Erro ao buscar loja: {e}")
        loja = {"nome": "Erro Loja", "cor_primaria": "#dc2626"}

    # 2. Busca Produtos (Filtrando por Loja e Status Publicado)
    # A query filtra: loja_id IGUAL ao definido E status IGUAL a published
    produtos = []
    try:
        query_url = f"{DIRECTUS_URL}/items/produtos?filter[loja_id][_eq]={LOJA_ID}&filter[status][_eq]=published"
        resp_prod = requests.get(query_url, headers=headers)
        
        if resp_prod.status_code == 200:
            produtos_raw = resp_prod.json().get('data', [])
            
            for p in produtos_raw:
                # Tratamento da Imagem Principal
                img_url = "https://via.placeholder.com/400?text=Sem+Foto"
                if p.get('imagem_destaque'):
                    img_url = f"{DIRECTUS_URL}/assets/{p['imagem_destaque']}"
                elif p.get('imagem1'): # Fallback para imagem antiga
                    img_url = f"{DIRECTUS_URL}/assets/{p['imagem1']}"

                # Tratamento das Variantes (Repeater JSON)
                # O Directus retorna uma lista de objetos [{nome: "Azul", foto: "ID"}]
                variantes_tratadas = []
                if p.get('variantes'):
                    for v in p['variantes']:
                        # URL da foto da variante
                        v_img = f"{DIRECTUS_URL}/assets/{v['foto']}" if v.get('foto') else img_url
                        variantes_tratadas.append({
                            "nome": v.get('nome', 'Padrão'),
                            "foto": v_img
                        })

                # Montagem do Objeto Final para o Template
                produtos.append({
                    "id": p['id'],
                    "nome": p['nome'],
                    "preco": float(p['preco']) if p.get('preco') else None, # Garante float ou None
                    "imagem": img_url,
                    "origem": p.get('origem', 'XBZ'), # XBZ, Mauro, Estoque Proprio
                    "urgencia": p.get('status_urgencia', 'Normal'), # Gatilho de escassez
                    "classe_frete": p.get('classe_frete', 'Pequeno'),
                    "variantes": variantes_tratadas,
                    "descricao": p.get('descricao', '')
                })
        else:
            print(f"Erro Directus Produtos: {resp_prod.text}")

    except Exception as e:
        print(f"Erro ao buscar produtos: {e}")

    # Renderiza o HTML passando as variáveis
    return render_template('index.html', loja=loja, produtos=produtos, directus_url=DIRECTUS_URL)

@app.route('/api/calcular-frete', methods=['POST'])
def calcular_frete():
    data = request.json
    cep_destino = data.get('cep')
    itens_carrinho = data.get('itens') # Lista vinda do JS

    if not cep_destino or not itens_carrinho:
        return jsonify({"erro": "Dados inválidos"}), 400

    # 1. Simulação de Cubagem (Empilhamento simples)
    peso_total = 0.0
    altura_total = 0.0
    largura_max = 0.0
    comprimento_max = 0.0
    valor_seguro = 0.0

    for item in itens_carrinho:
        classe = item.get('classe_frete', 'Pequeno')
        qtd = int(item.get('qtd', 1))
        # Pega dimensões da tabela, se não achar usa Pequeno
        medidas = DIMENSOES.get(classe, DIMENSOES['Pequeno'])
        
        peso_total += medidas['weight'] * qtd
        altura_total += medidas['height'] * qtd 
        largura_max = max(largura_max, medidas['width'])
        comprimento_max = max(comprimento_max, medidas['length'])
        
        # Valor do seguro (importante para transportadora)
        preco_item = item.get('preco', 0)
        if preco_item:
            valor_seguro += float(preco_item) * qtd

    # Limites mínimos dos Correios/Jadlog
    altura_total = max(altura_total, 4)
    largura_max = max(largura_max, 10)
    comprimento_max = max(comprimento_max, 15)
    valor_seguro = max(valor_seguro, 25.00) # Mínimo de declaração geralmente é R$ 25

    # 2. Chamada à API Melhor Envio
    url = "https://melhorenvio.com.br/api/v2/me/shipment/calculate"
    headers = {
        "Authorization": f"Bearer {MELHOR_ENVIO_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # Payload oficial do Melhor Envio
    payload = {
        "from": {"postal_code": "01026000"}, # CEP Genérico da 25 de Março
        "to": {"postal_code": cep_destino},
        "products": [{
            "id": "pacote-consolidado",
            "width": int(largura_max),
            "height": int(altura_total),
            "length": int(comprimento_max),
            "weight": peso_total,
            "insurance_value": valor_seguro,
            "quantity": 1
        }],
        "services": "1,2,3,4,17" # IDs comuns (Sedex, PAC, Jadlog...) - Opcional filtrar na request
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print("Erro API Melhor Envio:", response.text)
            return jsonify([]), 500
            
        cotacoes = response.json()
        opcoes_filtradas = []
        
        # Filtra e formata para o Frontend
        for c in cotacoes:
            if 'error' in c: continue # Pula erros
            
            # Pega apenas Correios e Jadlog (mais confiáveis para dropshipping)
            company = c.get('company', {}).get('name', '')
            
            if company in ['Correios', 'Jadlog', 'Loggi']:
                opcoes_filtradas.append({
                    "servico": c['name'],
                    "transportadora": company,
                    # Adiciona R$ 4,00 de margem para caixa/fita
                    "preco": float(c['price']) + 4.00, 
                    # Adiciona 2 dias de margem (Logística Seg/Qua)
                    "prazo": c['delivery_time'] + 2 
                })
        
        # Ordena pelo preço menor
        opcoes_filtradas.sort(key=lambda x: x['preco'])
        
        return jsonify(opcoes_filtradas)
        
    except Exception as e:
        print(f"Exception no Frete: {e}")
        return jsonify([]), 500

if __name__ == '__main__':
    # Rodar localmente
    app.run(debug=True, host='0.0.0.0', port=5000)