from flask import Flask, render_template, request, jsonify
import requests
import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
DIRECTUS_URL = os.getenv("DIRECTUS_URL", "https://api2.leanttro.com")
DIRECTUS_TOKEN = os.getenv("DIRECTUS_TOKEN", "") 
LOJA_ID = os.getenv("LOJA_ID", "") 

# CONFIGURAÇÕES SUPERFRETE
SUPERFRETE_TOKEN = os.getenv("SUPERFRETE_TOKEN", "")
SUPERFRETE_URL = os.getenv("SUPERFRETE_URL", "https://api.superfrete.com/api/v1/calculator")
CEP_ORIGEM = "01026000" # CEP da 25 de Março (Genérico)

# --- TABELA DE MEDIDAS (Simulação) ---
DIMENSOES = {
    "Pequeno": {"height": 4, "width": 12, "length": 16, "weight": 0.3}, # Envelope
    "Medio":   {"height": 10, "width": 20, "length": 20, "weight": 1.0}, # Caixa P
    "Grande":  {"height": 20, "width": 30, "length": 30, "weight": 3.0}  # Caixa G
}

@app.route('/')
def index():
    headers = {"Authorization": f"Bearer {DIRECTUS_TOKEN}"} if DIRECTUS_TOKEN else {}
    
    # 1. Busca Loja
    try:
        if LOJA_ID:
            resp_loja = requests.get(f"{DIRECTUS_URL}/items/lojas/{LOJA_ID}", headers=headers)
            loja = resp_loja.json().get('data', {}) if resp_loja.status_code == 200 else {}
        else:
            loja = {"nome": "Loja Demo", "cor_primaria": "#dc2626"}
    except:
        loja = {"nome": "Erro Loja", "cor_primaria": "#dc2626"}

    # 2. Busca Produtos
    produtos = []
    try:
        query_url = f"{DIRECTUS_URL}/items/produtos?filter[loja_id][_eq]={LOJA_ID}&filter[status][_eq]=published"
        resp_prod = requests.get(query_url, headers=headers)
        
        if resp_prod.status_code == 200:
            produtos_raw = resp_prod.json().get('data', [])
            
            for p in produtos_raw:
                # Tratamento Inteligente de Imagem (URL ou ID)
                img_raw = p.get('imagem_destaque') or p.get('imagem1')
                img_url = "https://via.placeholder.com/400?text=Sem+Foto"
                
                if img_raw:
                    if img_raw.startswith('http'):
                        img_url = img_raw
                    else:
                        img_url = f"{DIRECTUS_URL}/assets/{img_raw}"

                # Variantes (Cores)
                variantes_tratadas = []
                if p.get('variantes'):
                    for v in p['variantes']:
                        foto_val = v.get('foto')
                        v_img = img_url # Fallback
                        if foto_val:
                            v_img = foto_val if foto_val.startswith('http') else f"{DIRECTUS_URL}/assets/{foto_val}"
                        
                        variantes_tratadas.append({
                            "nome": v.get('nome', 'Padrão'),
                            "foto": v_img
                        })

                produtos.append({
                    "id": p['id'],
                    "nome": p['nome'],
                    "preco": float(p['preco']) if p.get('preco') else None,
                    "imagem": img_url,
                    "origem": p.get('origem', 'XBZ'),
                    "urgencia": p.get('status_urgencia', 'Normal'),
                    "classe_frete": p.get('classe_frete', 'Pequeno'),
                    "variantes": variantes_tratadas,
                    "descricao": p.get('descricao', '')
                })
    except Exception as e:
        print(f"Erro ao buscar produtos: {e}")

    return render_template('index.html', loja=loja, produtos=produtos, directus_url=DIRECTUS_URL)

@app.route('/api/calcular-frete', methods=['POST'])
def calcular_frete():
    data = request.json
    cep_destino = data.get('cep')
    itens_carrinho = data.get('itens')

    if not cep_destino or not itens_carrinho:
        return jsonify({"erro": "Dados inválidos"}), 400

    # 1. Consolida os volumes (Soma pesos para economizar)
    peso_total = 0.0
    altura_total = 0.0
    largura_max = 0.0
    comprimento_max = 0.0
    valor_seguro = 0.0

    for item in itens_carrinho:
        classe = item.get('classe_frete', 'Pequeno')
        qtd = int(item.get('qtd', 1))
        medidas = DIMENSOES.get(classe, DIMENSOES['Pequeno'])
        
        peso_total += medidas['weight'] * qtd
        altura_total += medidas['height'] * qtd 
        largura_max = max(largura_max, medidas['width'])
        comprimento_max = max(comprimento_max, medidas['length'])
        
        if item.get('preco'):
            valor_seguro += float(item['preco']) * qtd

    # Ajustes Mínimos dos Correios (SuperFrete usa Correios)
    altura_total = max(altura_total, 2)
    largura_max = max(largura_max, 11)
    comprimento_max = max(comprimento_max, 16)
    peso_total = max(peso_total, 0.3) # Mínimo 300g
    valor_seguro = max(valor_seguro, 25.00) # Valor declarado mínimo

    # 2. Chama API SuperFrete
    # IMPORTANTE: Verifique na documentação deles se os nomes dos campos (keys) são exatamente estes.
    # A estrutura abaixo é a padrão do mercado (Melhor Envio/Kangu/Etc).
    
    payload = {
        "from": { "postal_code": CEP_ORIGEM },
        "to": { "postal_code": cep_destino },
        "services": "PAC,SEDEX,MINI", # Filtra o que você quer
        "options": {
            "own_hand": False, # Mão própria
            "receipt": False,  # Aviso de recebimento
            "insurance_value": valor_seguro # Valor declarado
        },
        "package": {
            "height": int(altura_total),
            "width": int(largura_max),
            "length": int(comprimento_max),
            "weight": peso_total
        }
    }
    
    # Se a doc pedir token no Header, costuma ser assim:
    headers = {
        "Authorization": f"Bearer {SUPERFRETE_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        # Timeout curto para não travar o site
        response = requests.post(SUPERFRETE_URL, json=payload, headers=headers, timeout=8)
        
        if response.status_code != 200:
            print(f"Erro SuperFrete: {response.status_code} - {response.text}")
            # Retorna lista vazia para o front tratar (mostrar 'Combine no Zap')
            return jsonify([]), 500

        cotacoes = response.json()
        opcoes = []

        # Adapta a resposta deles para o nosso padrão
        # A resposta geralmente é uma lista [ {name: "PAC", price: 20.00...} ]
        # Se a estrutura for diferente (ex: keys em portugues), ajuste abaixo.
        
        # Exemplo de tratamento genérico (Itera sobre a lista que eles devolverem)
        lista_retorno = cotacoes if isinstance(cotacoes, list) else cotacoes.get('shipping_options', [])

        for c in lista_retorno:
            # Pega o nome (PAC/Sedex) e o Preço
            nome_servico = c.get('name') or c.get('service', {}).get('name') or 'Entrega'
            preco_api = c.get('price') or c.get('custom_price') or 0
            prazo_api = c.get('delivery_time') or c.get('days') or 5

            if preco_api:
                opcoes.append({
                    "servico": nome_servico,
                    "transportadora": "Correios", # SuperFrete é basicamente Correios
                    "preco": float(preco_api) + 4.00, # + R$ 4,00 (Embalagem)
                    "prazo": int(prazo_api) + 2       # + 2 Dias (Sua logística)
                })

        # Ordena (Mais barato primeiro)
        opcoes.sort(key=lambda x: x['preco'])
        
        return jsonify(opcoes)

    except Exception as e:
        print(f"Exception Calculo Frete: {e}")
        return jsonify([]), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)