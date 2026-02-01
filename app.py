from flask import Flask, render_template, request, jsonify
import requests
import os
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# --- CONFIGURAÇÕES GERAIS ---
DIRECTUS_URL = os.getenv("DIRECTUS_URL", "https://api2.leanttro.com")
DIRECTUS_TOKEN = os.getenv("DIRECTUS_TOKEN", "") 
LOJA_ID = os.getenv("LOJA_ID", "") 

# --- CONFIGURAÇÕES SUPERFRETE (Doc Oficial) ---
SUPERFRETE_TOKEN = os.getenv("SUPERFRETE_TOKEN", "")
# URL Padrão (Se for produção, remova o 'sandbox.' da URL no .env)
# Pela sua doc: https://sandbox.superfrete.com/api/v0/calculator
SUPERFRETE_URL = os.getenv("SUPERFRETE_URL", "https://api.superfrete.com/api/v0/calculator")
CEP_ORIGEM = "01026000" # CEP da 25 de Março

# --- TABELA DE MEDIDAS (Simulação) ---
DIMENSOES = {
    "Pequeno": {"height": 4, "width": 12, "length": 16, "weight": 0.3}, # Envelope
    "Medio":   {"height": 10, "width": 20, "length": 20, "weight": 1.0}, # Caixa P
    "Grande":  {"height": 20, "width": 30, "length": 30, "weight": 3.0}  # Caixa G
}

# --- FUNÇÃO AUXILIAR DE IMAGEM ---
def get_img_url(image_id_or_url):
    """
    Trata ID do Directus ou URL externa.
    Se for URL completa (http...), retorna ela mesma.
    Se for ID do Directus, monta a URL de assets.
    """
    if not image_id_or_url:
        return "https://via.placeholder.com/800x400?text=Sem+Imagem"
    
    if image_id_or_url.startswith('http'):
        return image_id_or_url
    
    return f"{DIRECTUS_URL}/assets/{image_id_or_url}"

# --- ROTA: PÁGINA INICIAL (LOJA) ---
@app.route('/')
def index():
    headers = {"Authorization": f"Bearer {DIRECTUS_TOKEN}"} if DIRECTUS_TOKEN else {}
    
    # 1. BUSCA DADOS DA LOJA (Incluindo Banners)
    loja = {}
    try:
        if LOJA_ID:
            # Pega todos os campos (*.*) para garantir que banners venham
            resp_loja = requests.get(f"{DIRECTUS_URL}/items/lojas/{LOJA_ID}?fields=*.*", headers=headers)
            if resp_loja.status_code == 200:
                data = resp_loja.json().get('data', {})
                loja = {
                    "nome": data.get('nome', 'Minha Loja'),
                    "logo": data.get('logo'),
                    "cor_primaria": data.get('cor_primaria', '#dc2626'),
                    "whatsapp": data.get('whatsapp_comercial') or '5511999999999',
                    # Banners Principais
                    "banner1": get_img_url(data.get('bannerprincipal1')),
                    "link1": data.get('linkbannerprincipal1', '#'),
                    "banner2": get_img_url(data.get('bannerprincipal2')) if data.get('bannerprincipal2') else None,
                    "link2": data.get('linkbannerprincipal2', '#'),
                    # Banners Menores
                    "bannermenor1": get_img_url(data.get('bannermenor1')),
                    "bannermenor2": get_img_url(data.get('bannermenor2'))
                }
        else:
            loja = {"nome": "Configure o LOJA_ID", "cor_primaria": "#dc2626"}
    except Exception as e:
        print(f"Erro Loja: {e}")
        loja = {"nome": "Erro Carregamento", "cor_primaria": "#dc2626"}

    # 2. BUSCA CATEGORIAS
    categorias = []
    try:
        url_cat = f"{DIRECTUS_URL}/items/categorias?filter[loja_id][_eq]={LOJA_ID}&filter[status][_eq]=published"
        resp_cat = requests.get(url_cat, headers=headers)
        if resp_cat.status_code == 200:
            categorias = resp_cat.json().get('data', [])
    except Exception as e:
        print(f"Erro Categorias: {e}")

    # 3. BUSCA POSTS (BLOG) - Limite 3 para a Home
    posts = []
    try:
        url_posts = f"{DIRECTUS_URL}/items/posts?filter[loja_id][_eq]={LOJA_ID}&filter[status][_eq]=published&limit=3&sort=-date_created"
        resp_posts = requests.get(url_posts, headers=headers)
        if resp_posts.status_code == 200:
            raw_posts = resp_posts.json().get('data', [])
            for p in raw_posts:
                # Formata data
                data_fmt = "Recente"
                if p.get('date_created'):
                    try:
                        dt = datetime.fromisoformat(p['date_created'].replace('Z', '+00:00'))
                        data_fmt = dt.strftime('%d.%m.%Y')
                    except: pass

                posts.append({
                    "titulo": p.get('titulo'),
                    "resumo": p.get('resumo'),
                    "capa": get_img_url(p.get('capa')),
                    "slug": p.get('slug'),
                    "data": data_fmt
                })
    except Exception as e:
        print(f"Erro Posts: {e}")

    # 4. BUSCA PRODUTOS
    produtos = []
    try:
        url_prod = f"{DIRECTUS_URL}/items/produtos?filter[loja_id][_eq]={LOJA_ID}&filter[status][_eq]=published"
        resp_prod = requests.get(url_prod, headers=headers)
        
        if resp_prod.status_code == 200:
            produtos_raw = resp_prod.json().get('data', [])
            
            for p in produtos_raw:
                img_url = get_img_url(p.get('imagem_destaque') or p.get('imagem1'))

                # Variantes
                variantes_tratadas = []
                if p.get('variantes'):
                    for v in p['variantes']:
                        variantes_tratadas.append({
                            "nome": v.get('nome', 'Padrão'),
                            "foto": get_img_url(v.get('foto')) if v.get('foto') else img_url
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
        print(f"Erro Produtos: {e}")

    return render_template('index.html', loja=loja, categorias=categorias, posts=posts, produtos=produtos, directus_url=DIRECTUS_URL)

# --- ROTA: PÁGINA DO BLOG ---
@app.route('/blog')
def blog():
    headers = {"Authorization": f"Bearer {DIRECTUS_TOKEN}"} if DIRECTUS_TOKEN else {}
    
    # 1. Busca Loja (Para manter o Header/Footer igual ao site principal)
    loja = {}
    try:
        if LOJA_ID:
            resp_loja = requests.get(f"{DIRECTUS_URL}/items/lojas/{LOJA_ID}?fields=*.*", headers=headers)
            if resp_loja.status_code == 200:
                data = resp_loja.json().get('data', {})
                loja = {
                    "nome": data.get('nome', 'Blog'),
                    "logo": data.get('logo'),
                    "cor_primaria": data.get('cor_primaria', '#dc2626'),
                    "whatsapp": data.get('whatsapp_comercial') or '5511999999999'
                }
        else:
            loja = {"nome": "Blog", "cor_primaria": "#dc2626"}
    except:
        loja = {"nome": "Erro", "cor_primaria": "#dc2626"}

    # 2. Busca Categorias (Para o Menu)
    categorias = []
    try:
        url_cat = f"{DIRECTUS_URL}/items/categorias?filter[loja_id][_eq]={LOJA_ID}&filter[status][_eq]=published"
        resp_cat = requests.get(url_cat, headers=headers)
        if resp_cat.status_code == 200:
            categorias = resp_cat.json().get('data', [])
    except: pass

    # 3. Busca TODOS os Posts (Sem limite)
    posts = []
    try:
        url_posts = f"{DIRECTUS_URL}/items/posts?filter[loja_id][_eq]={LOJA_ID}&filter[status][_eq]=published&sort=-date_created"
        resp_posts = requests.get(url_posts, headers=headers)
        if resp_posts.status_code == 200:
            raw_posts = resp_posts.json().get('data', [])
            for p in raw_posts:
                data_fmt = "Recente"
                if p.get('date_created'):
                    try:
                        dt = datetime.fromisoformat(p['date_created'].replace('Z', '+00:00'))
                        data_fmt = dt.strftime('%d.%m.%Y')
                    except: pass

                posts.append({
                    "titulo": p.get('titulo'),
                    "resumo": p.get('resumo'),
                    "conteudo": p.get('conteudo'), # Traz o conteúdo completo
                    "capa": get_img_url(p.get('capa')),
                    "slug": p.get('slug'),
                    "data": data_fmt
                })
    except Exception as e:
        print(f"Erro Blog: {e}")

    return render_template('blog.html', loja=loja, categorias=categorias, posts=posts, directus_url=DIRECTUS_URL)

# --- ROTA: API DE CÁLCULO DE FRETE (SUPERFRETE) ---
@app.route('/api/calcular-frete', methods=['POST'])
def calcular_frete():
    data = request.json
    cep_destino = data.get('cep')
    itens_carrinho = data.get('itens')

    if not cep_destino or not itens_carrinho:
        return jsonify({"erro": "Dados inválidos"}), 400

    # 1. Consolida volumes
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

    # Ajustes Mínimos para Correios
    altura_total = max(altura_total, 2)
    largura_max = max(largura_max, 11)
    comprimento_max = max(comprimento_max, 16)
    peso_total = max(peso_total, 0.3)
    valor_seguro = max(valor_seguro, 25.00)

    # 2. Configurações da API SuperFrete (Conforme Doc)
    # IMPORTANTE: A Doc pede User-Agent específico e Token Bearer
    headers = {
        "Authorization": f"Bearer {SUPERFRETE_TOKEN}",
        "User-Agent": "Leanttro Store (suporte@leanttro.com)", # <--- OBRIGATÓRIO SEGUNDO A DOC
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    payload = {
        "from": { "postal_code": CEP_ORIGEM },
        "to": { "postal_code": cep_destino },
        "services": "PAC,SEDEX",
        "options": {
            "own_hand": False,
            "receipt": False,
            "insurance_value": valor_seguro
        },
        "package": {
            "height": int(altura_total),
            "width": int(largura_max),
            "length": int(comprimento_max),
            "weight": peso_total
        }
    }

    try:
        response = requests.post(SUPERFRETE_URL, json=payload, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"Erro SuperFrete ({response.status_code}): {response.text}")
            return jsonify([]), 500

        cotacoes = response.json()
        opcoes = []

        # Tenta pegar a lista de diferentes formas (caso a doc varie)
        lista_retorno = []
        if isinstance(cotacoes, list):
            lista_retorno = cotacoes
        elif 'shipping_options' in cotacoes:
            lista_retorno = cotacoes['shipping_options']
        else:
            # Tenta pegar direto se vier um objeto único
            lista_retorno = [cotacoes]

        for c in lista_retorno:
            # Tratamento de erros específicos na resposta (ex: area de risco)
            if 'error' in c and c['error']: continue

            nome_servico = c.get('name') or c.get('service', {}).get('name') or 'Entrega'
            preco_api = c.get('price') or c.get('custom_price') or c.get('vlrFrete')
            prazo_api = c.get('delivery_time') or c.get('days') or c.get('prazoEnt')

            if preco_api:
                opcoes.append({
                    "servico": nome_servico,
                    "transportadora": "Correios", 
                    "preco": float(preco_api) + 4.00, # Margem Embalagem
                    "prazo": int(prazo_api) + 2       # Margem Logística
                })

        # Ordena do mais barato para o mais caro
        opcoes.sort(key=lambda x: x['preco'])
        return jsonify(opcoes)

    except Exception as e:
        print(f"Exception Frete: {e}")
        return jsonify([]), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)