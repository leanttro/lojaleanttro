from flask import Flask, render_template, request, jsonify
import requests
import os
from datetime import datetime
from dotenv import load_dotenv
import traceback
import json

# Carrega variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# --- CONFIGURAÇÕES GERAIS ---
# Garante que a URL não tenha barra no final para evitar erros de //
raw_url = os.getenv("DIRECTUS_URL", "https://api2.leanttro.com")
DIRECTUS_URL = raw_url.rstrip('/')

DIRECTUS_TOKEN = os.getenv("DIRECTUS_TOKEN", "") 
LOJA_ID = os.getenv("LOJA_ID", "") 

# --- CONFIGURAÇÕES SUPERFRETE ---
SUPERFRETE_TOKEN = os.getenv("SUPERFRETE_TOKEN", "")
SUPERFRETE_URL = os.getenv("SUPERFRETE_URL", "https://api.superfrete.com/api/v0/calculator")
CEP_ORIGEM = "01026000" # CEP da 25 de Março

# --- TABELA DE MEDIDAS (Simulação) ---
DIMENSOES = {
    "Pequeno": {"height": 4, "width": 12, "length": 16, "weight": 0.3},
    "Medio":   {"height": 10, "width": 20, "length": 20, "weight": 1.0},
    "Grande":  {"height": 20, "width": 30, "length": 30, "weight": 3.0}
}

# --- FUNÇÃO AUXILIAR DE IMAGEM ---
def get_img_url(image_id_or_url):
    """
    Trata ID do Directus ou URL externa.
    """
    if not image_id_or_url:
        return "https://via.placeholder.com/800x400?text=Sem+Imagem"
    
    if isinstance(image_id_or_url, dict):
        return f"{DIRECTUS_URL}/assets/{image_id_or_url.get('id')}"
    
    if image_id_or_url.startswith('http'):
        return image_id_or_url
    
    return f"{DIRECTUS_URL}/assets/{image_id_or_url}"

# --- HELPER: BUSCAR DADOS DA LOJA ---
def get_loja_data(headers):
    try:
        if LOJA_ID:
            resp_loja = requests.get(f"{DIRECTUS_URL}/items/lojas/{LOJA_ID}?fields=*.*", headers=headers)
            if resp_loja.status_code == 200:
                data = resp_loja.json().get('data', {})
                
                logo_raw = data.get('logo')
                logo_final = logo_raw.get('id') if isinstance(logo_raw, dict) else logo_raw
                
                return {
                    "nome": data.get('nome', 'Minha Loja'),
                    "logo": logo_final,
                    "cor_primaria": data.get('cor_primaria', '#dc2626'),
                    "whatsapp": data.get('whatsapp_comercial') or '5511999999999',
                    "banner1": get_img_url(data.get('bannerprincipal1')),
                    "link1": data.get('linkbannerprincipal1', '#'),
                    "banner2": get_img_url(data.get('bannerprincipal2')) if data.get('bannerprincipal2') else None,
                    "link2": data.get('linkbannerprincipal2', '#'),
                    "bannermenor1": get_img_url(data.get('bannermenor1')),
                    "bannermenor2": get_img_url(data.get('bannermenor2'))
                }
    except Exception as e:
        print(f"Erro Loja: {e}")
    return {"nome": "Loja", "cor_primaria": "#dc2626", "whatsapp": ""}

# --- HELPER: BUSCAR CATEGORIAS ---
def get_categorias(headers):
    try:
        url_cat = f"{DIRECTUS_URL}/items/categorias?filter[loja_id][_eq]={LOJA_ID}&filter[status][_eq]=published"
        resp_cat = requests.get(url_cat, headers=headers)
        if resp_cat.status_code == 200:
            return resp_cat.json().get('data', [])
    except: pass
    return []

# --- ROTA: HOME (INDEX) ---
@app.route('/presentes/')
def index():
    headers = {"Authorization": f"Bearer {DIRECTUS_TOKEN}"} if DIRECTUS_TOKEN else {}
    
    loja = get_loja_data(headers)
    categorias = get_categorias(headers)
    
    cat_filter = request.args.get('categoria')
    filter_str = f"&filter[loja_id][_eq]={LOJA_ID}&filter[status][_eq]=published"
    if cat_filter:
        filter_str += f"&filter[categoria_id][_eq]={cat_filter}"

    produtos = []
    novidades = []

    try:
        url_prod = f"{DIRECTUS_URL}/items/produtos?{filter_str}"
        resp_prod = requests.get(url_prod, headers=headers)
        
        if resp_prod.status_code == 200:
            produtos_raw = resp_prod.json().get('data', [])
            for p in produtos_raw:
                img_url = get_img_url(p.get('imagem_destaque') or p.get('imagem1'))
                
                variantes_tratadas = []
                if p.get('variantes'):
                    for v in p['variantes']:
                        v_img = get_img_url(v.get('foto')) if v.get('foto') else img_url
                        variantes_tratadas.append({"nome": v.get('nome', 'Padrão'), "foto": v_img})

                specs = p.get('especificacoes')
                is_novidade = False
                ordem_novidade = 9999

                try:
                    if specs and isinstance(specs, str):
                        specs = json.loads(specs)
                    
                    if isinstance(specs, dict):
                        if specs.get('novidade') == True:
                            is_novidade = True
                            ordem_novidade = int(specs.get('ordem', 9999))
                except:
                    pass

                prod_obj = {
                    "id": str(p['id']), 
                    "nome": p['nome'],
                    "slug": p.get('slug'),
                    "preco": float(p['preco']) if p.get('preco') else None,
                    "imagem": img_url,
                    "origem": p.get('origem', 'XBZ'),
                    "urgencia": p.get('status_urgencia', 'Normal'),
                    "classe_frete": p.get('classe_frete', 'Pequeno'),
                    "variantes": variantes_tratadas,
                    "descricao": p.get('descricao', ''),
                    "categoria_id": p.get('categoria_id'),
                    "ordem_novidade": ordem_novidade
                }

                produtos.append(prod_obj)
                if is_novidade:
                    novidades.append(prod_obj)
            
            novidades.sort(key=lambda x: x['ordem_novidade'])

    except Exception as e:
        print(f"Erro Produtos: {e}")

    posts = []
    try:
        url_posts = f"{DIRECTUS_URL}/items/posts?filter[loja_id][_eq]={LOJA_ID}&filter[status][_eq]=published&limit=3&sort=-date_created"
        resp_posts = requests.get(url_posts, headers=headers)
        if resp_posts.status_code == 200:
            raw_posts = resp_posts.json().get('data', [])
            for p in raw_posts:
                data_fmt = "Recente"
                if p.get('date_created'):
                    try: dt = datetime.fromisoformat(p['date_created'].replace('Z', '+00:00')); data_fmt = dt.strftime('%d.%m.%Y')
                    except: pass
                posts.append({
                    "titulo": p.get('titulo'),
                    "resumo": p.get('resumo'),
                    "capa": get_img_url(p.get('capa')),
                    "slug": p.get('slug'),
                    "data": data_fmt
                })
    except: pass

    return render_template('index.html', loja=loja, categorias=categorias, produtos=produtos, novidades=novidades, posts=posts, directus_url=DIRECTUS_URL)

# --- ROTA: PÁGINA DE PRODUTO ---
@app.route('/presentes/produto/<slug>')
def produto(slug):
    headers = {"Authorization": f"Bearer {DIRECTUS_TOKEN}"} if DIRECTUS_TOKEN else {}
    
    loja = get_loja_data(headers)
    categorias = get_categorias(headers)
    
    product_data = None
    try:
        url_p = f"{DIRECTUS_URL}/items/produtos?filter[slug][_eq]={slug}&filter[loja_id][_eq]={LOJA_ID}"
        resp = requests.get(url_p, headers=headers)
        if resp.status_code == 200 and len(resp.json()['data']) > 0:
            p = resp.json()['data'][0]
            
            galeria = []
            if p.get('imagem_destaque'): galeria.append(get_img_url(p['imagem_destaque']))
            if p.get('imagem1'): galeria.append(get_img_url(p['imagem1']))
            if p.get('imagem2'): galeria.append(get_img_url(p['imagem2']))
            if p.get('imagem3'): galeria.append(get_img_url(p['imagem3']))
            if not galeria: galeria.append("https://via.placeholder.com/800x800?text=Sem+Foto")

            variantes_tratadas = []
            if p.get('variantes'):
                for v in p['variantes']:
                    v_img = get_img_url(v.get('foto')) if v.get('foto') else galeria[0]
                    variantes_tratadas.append({"nome": v.get('nome', 'Padrão'), "foto": v_img})

            product_data = {
                "id": str(p['id']),
                "nome": p['nome'],
                "slug": p.get('slug'),
                "preco": float(p['preco']) if p.get('preco') else None,
                "galeria": galeria,
                "origem": p.get('origem', 'XBZ'),
                "classe_frete": p.get('classe_frete', 'Pequeno'),
                "variantes": variantes_tratadas,
                "descricao": p.get('descricao', ''),
                "especificacoes": p.get('especificacoes', '')
            }
        else:
            return "Produto não encontrado", 404
    except Exception as e:
        print(f"ERRO PRODUTO: {e}")
        return f"Erro interno: {e}", 500

    return render_template('produtos.html', loja=loja, categorias=categorias, p=product_data, directus_url=DIRECTUS_URL)

# --- ROTA: BLOG POST ---
@app.route('/presentes/blog/<slug>')
def blog_post(slug):
    headers = {"Authorization": f"Bearer {DIRECTUS_TOKEN}"} if DIRECTUS_TOKEN else {}
    loja = get_loja_data(headers)
    categorias = get_categorias(headers)
    
    post_data = None
    try:
        url_post = f"{DIRECTUS_URL}/items/posts?filter[slug][_eq]={slug}&filter[loja_id][_eq]={LOJA_ID}&filter[status][_eq]=published"
        resp = requests.get(url_post, headers=headers)
        
        if resp.status_code == 200 and len(resp.json()['data']) > 0:
            p = resp.json()['data'][0]
            data_fmt = "Recente"
            if p.get('date_created'):
                try: dt = datetime.fromisoformat(p['date_created'].replace('Z', '+00:00')); data_fmt = dt.strftime('%d.%m.%Y')
                except: pass
            
            post_data = {
                "titulo": p.get('titulo'),
                "conteudo": p.get('conteudo'),
                "resumo": p.get('resumo'),
                "capa": get_img_url(p.get('capa')),
                "data": data_fmt,
                "autor": "Equipe " + loja['nome']
            }
        else:
            return "Artigo não encontrado", 404
            
        return render_template('blog.html', loja=loja, categorias=categorias, post=post_data, directus_url=DIRECTUS_URL)

    except Exception as e:
        print(f"Erro Post: {e}")
        return "Erro interno", 500

@app.route('/presentes/blog')
def blog_list():
    return index() 

# --- ROTA: CÁLCULO DE FRETE (CORRIGIDA E BLINDADA CONTRA ERRO 500) ---
@app.route('/presentes/api/calcular-frete', methods=['POST'])
def calcular_frete():
    data = request.json
    cep_destino = data.get('cep')
    itens_carrinho = data.get('itens')

    if not cep_destino or not itens_carrinho:
        return jsonify({"erro": "Dados inválidos"}), 400

    peso_total = 0.0
    altura_total = 0.0
    largura_max = 0.0
    comprimento_max = 0.0
    valor_seguro = 0.0

    for item in itens_carrinho:
        classe = item.get('classe_frete', 'Pequeno')
        qtd = int(item.get('qtd', 1))
        # Usa .get para evitar erro se a chave não existir
        medidas = DIMENSOES.get(classe, DIMENSOES['Pequeno'])
        
        peso_total += medidas['weight'] * qtd
        altura_total += medidas['height'] * qtd 
        largura_max = max(largura_max, medidas['width'])
        comprimento_max = max(comprimento_max, medidas['length'])
        if item.get('preco'): 
            valor_seguro += float(item['preco']) * qtd

    # Garante inteiros para dimensões e float controlado para peso
    altura_total = int(max(altura_total, 2))
    largura_max = int(max(largura_max, 11))
    comprimento_max = int(max(comprimento_max, 16))
    peso_total = round(max(peso_total, 0.3), 2)
    valor_seguro = max(valor_seguro, 25.00)

    headers = {
        "Authorization": f"Bearer {SUPERFRETE_TOKEN}",
        "User-Agent": "Leanttro Store (suporte@leanttro.com)",
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
            "height": altura_total, 
            "width": largura_max, 
            "length": comprimento_max, 
            "weight": peso_total 
        }
    }

    try:
        # Timeout adicionado para evitar travamento infinito
        response = requests.post(SUPERFRETE_URL, json=payload, headers=headers, timeout=10)
        
        # BLINDAGEM: Se o status não for 200, não tenta ler JSON (evita o crash 500)
        if response.status_code != 200:
            print(f"ERRO SUPERFRETE API ({response.status_code}): {response.text}")
            return jsonify({"erro": "Erro na API de Frete", "detalhes": response.text}), response.status_code

        # Se chegou aqui, é seguro tentar ler o JSON
        try:
            cotacoes = response.json()
        except json.JSONDecodeError:
            print(f"ERRO JSON SUPERFRETE: {response.text}")
            return jsonify({"erro": "Resposta inválida da transportadora"}), 502

        opcoes = []
        lista_retorno = []
        
        if isinstance(cotacoes, list):
            lista_retorno = cotacoes
        elif isinstance(cotacoes, dict):
            if 'shipping_options' in cotacoes:
                lista_retorno = cotacoes['shipping_options']
            else:
                lista_retorno = [cotacoes]

        for c in lista_retorno:
            if isinstance(c, dict) and c.get('error'): continue
            
            nome = c.get('name') or c.get('service', {}).get('name')
            preco = c.get('price') or c.get('custom_price') or c.get('vlrFrete')
            prazo = c.get('delivery_time') or c.get('days') or c.get('prazoEnt')

            if nome and preco:
                opcoes.append({
                    "servico": nome,
                    "transportadora": "Correios", 
                    "preco": float(preco) + 4.00,
                    "prazo": int(prazo or 10) + 2
                })

        opcoes.sort(key=lambda x: x['preco'])
        return jsonify(opcoes)

    except requests.exceptions.Timeout:
        return jsonify({"erro": "Tempo limite excedido ao calcular frete"}), 504
    except Exception as e:
        print(f"ERRO INTERNO GERAL: {e}")
        traceback.print_exc()
        return jsonify({"erro": "Erro interno no servidor", "msg": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)