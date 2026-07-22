import http.server
import socketserver
import re
import zipfile
import io
import csv

# ==========================================
# 1. O FRONTEND (HTML + CSS + JavaScript)
# ==========================================
HTML_PAGE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Conversor de VLANs (Lote ZIP)</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #001f3f 0%, #003366 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            color: #333;
        }
        .caixa-busca {
            background-color: #ffffff;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 15px 30px rgba(0,0,0,0.4);
            text-align: center;
            max-width: 450px;
            width: 90%;
            border-top: 6px solid #FFC107; 
        }
        h2 { 
            color: #001f3f;
            margin-top: 0;
            margin-bottom: 10px; 
            font-weight: 800;
            letter-spacing: -0.5px;
        }
        p { 
            color: #555; 
            margin-bottom: 30px; 
            font-size: 15px; 
            line-height: 1.5;
        }
        input[type="file"] {
            display: block;
            margin: 0 auto 20px auto;
            padding: 15px;
            border: 2px dashed #001f3f;
            border-radius: 8px;
            background-color: #f8f9fa;
            cursor: pointer;
            width: 100%;
            box-sizing: border-box;
            color: #001f3f;
            font-weight: 600;
            transition: background-color 0.3s ease;
        }
        input[type="file"]:hover {
            background-color: #eef2f5;
        }
        button {
            background-color: #FFC107;
            color: #001f3f;
            border: none;
            padding: 14px 20px;
            font-size: 16px;
            font-weight: 900;
            border-radius: 8px;
            cursor: pointer;
            width: 100%;
            transition: all 0.3s ease;
            box-shadow: 0 4px 6px rgba(255, 193, 7, 0.3);
            text-transform: uppercase;
        }
        button:hover { 
            background-color: #ffca28;
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(255, 193, 7, 0.4);
        }
        button:active {
            transform: translateY(0);
            box-shadow: 0 2px 4px rgba(255, 193, 7, 0.3);
        }
        #mensagem { 
            margin-top: 20px; 
            font-weight: bold; 
            font-size: 14px;
            padding: 10px;
            border-radius: 6px;
            display: none;
        }
    </style>
</head>
<body>

    <div class="caixa-busca">
        <h2>Extrator de VLANs (ZIP)</h2>
        <p>Selecione um arquivo <b>.zip</b> contendo seus backups para gerar o relatório <b>CSV</b> com sugestão de padronização.</p>
        
        <input type="file" id="arquivoInput" accept=".zip">
        <button onclick="processarArquivo()">Processar ZIP e Baixar CSV</button>
        
        <div id="mensagem"></div>
    </div>

    <script>
        function processarArquivo() {
            const input = document.getElementById('arquivoInput');
            const mensagem = document.getElementById('mensagem');
            
            mensagem.style.display = "block";

            if (input.files.length === 0) {
                mensagem.style.backgroundColor = "#ffeeba";
                mensagem.style.color = "#856404";
                mensagem.innerText = "Por favor, selecione um arquivo .zip primeiro!";
                return;
            }

            const file = input.files[0];
            const reader = new FileReader();

            reader.onload = function(evento) {
                const arrayBuffer = evento.target.result;
                
                mensagem.style.backgroundColor = "#e8f4f8";
                mensagem.style.color = "#001f3f";
                mensagem.innerText = "Processando lote de arquivos. Aguarde...";

                fetch('/', {
                    method: 'POST',
                    body: arrayBuffer,
                    headers: {
                        'Content-Type': 'application/zip'
                    }
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error("Não foi possível processar o ZIP ou encontrar VLANs.");
                    }
                    return response.blob();
                })
                .then(blob => {
                    mensagem.style.backgroundColor = "#d4edda";
                    mensagem.style.color = "#155724";
                    mensagem.innerText = "Sucesso! Baixando planilha CSV...";
                    
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    
                    const nomeSemExtensao = file.name.substring(0, file.name.lastIndexOf('.')) || file.name;
                    a.download = nomeSemExtensao + "_relatorio_vlans.csv";
                    
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                })
                .catch(erro => {
                    mensagem.style.backgroundColor = "#f8d7da";
                    mensagem.style.color = "#721c24";
                    mensagem.innerText = erro.message;
                });
            };

            reader.readAsArrayBuffer(file);
        }
    </script>
</body>
</html>
"""

# ==========================================
# 2. O BACKEND (A Lógica em Python)
# ==========================================

def obter_sugestao_nome(nome_original):
    """
    Analisa o nome original da VLAN e retorna a sugestão padronizada.
    """
    nome_lower = nome_original.lower()
    
    if "ipoe" in nome_lower:
        return "NET_DHCP"
    elif "voip" in nome_lower:
        return "TEL_BRISA"
    elif "iptv" in nome_lower:
        return "IPTV_BRISA"
    elif "internet" in nome_lower:
        return "NET_PPPOE"
    
    return "" # Deixa em branco caso não seja nenhuma dessas

def processar_zip_para_csv(dados_binarios_zip):
    # Regex 1: Huawei/Datacom (Captura Grupo 1 (Nome) e Grupo 2 (ID))
    padrao_vlan1 = re.compile(r"^service-vlan\s+(\S+)\s+(\d+)\s+to\s+\d+\s+type\s+\S+", re.MULTILINE)
    
    # Regex 2: FiberHome (Captura Grupo 1 (ID) e Grupo 2 (Nome))
    padrao_vlan2 = re.compile(r"^set\s+service_vlan\s+(\d+)\s+(\S+)\s+type\s+\S+", re.MULTILINE)
    
    # Regras para buscar Nome e IP da OLT
    padrao_hostname = re.compile(r"^hostname\s+(\S+)", re.MULTILINE)
    padrao_ip = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})")

    linhas_csv = []
    # Atualizado: Agora com 5 colunas, incluindo a Sugestão
    linhas_csv.append(["Nome da OLT", "IP da OLT", "Nome da VLAN", "ID da VLAN", "Sugestão de Nome"])

    with zipfile.ZipFile(io.BytesIO(dados_binarios_zip)) as arquivo_zip:
        for nome_arquivo in arquivo_zip.namelist():
            if nome_arquivo.endswith('/'):
                continue
            
            try:
                conteudo_arquivo = arquivo_zip.read(nome_arquivo).decode('utf-8', errors='ignore')
            except Exception:
                continue

            match_ip = padrao_ip.search(nome_arquivo)
            ip_olt = match_ip.group(1) if match_ip else "IP Não Encontrado"

            match_hostname = padrao_hostname.search(conteudo_arquivo)
            nome_olt = match_hostname.group(1) if match_hostname else "Nome Não Encontrado"

            # Processa Padrão 1 (Huawei/Datacom)
            matches_vlan1 = padrao_vlan1.findall(conteudo_arquivo)
            for match in matches_vlan1:
                nome_vlan = match[0]
                id_vlan = match[1]
                sugestao = obter_sugestao_nome(nome_vlan)
                linhas_csv.append([nome_olt, ip_olt, nome_vlan, id_vlan, sugestao])

            # Processa Padrão 2 (FiberHome)
            matches_vlan2 = padrao_vlan2.findall(conteudo_arquivo)
            for match in matches_vlan2:
                id_vlan = match[0]  # No Fiberhome, o número vem primeiro
                nome_vlan = match[1]
                sugestao = obter_sugestao_nome(nome_vlan)
                linhas_csv.append([nome_olt, ip_olt, nome_vlan, id_vlan, sugestao])

    return linhas_csv

class ServidorExtrator(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode("utf-8"))

    def do_POST(self):
        try:
            tamanho_conteudo = int(self.headers['Content-Length'])
            dados_zip = self.rfile.read(tamanho_conteudo)
            
            linhas_extraidas = processar_zip_para_csv(dados_zip)
            
            if len(linhas_extraidas) <= 1:
                self.send_response(400)
                self.end_headers()
                return

            saida_csv_memoria = io.StringIO()
            # Mantemos o ponto e vírgula, padrão do Excel em PT-BR
            escritor_csv = csv.writer(saida_csv_memoria, delimiter=';')
            escritor_csv.writerows(linhas_extraidas)

            texto_final_csv = saida_csv_memoria.getvalue()

            self.send_response(200)
            self.send_header("Content-type", "text/csv; charset=utf-8-sig") 
            self.end_headers()
            self.wfile.write(texto_final_csv.encode("utf-8-sig"))
            
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            print(f"Erro no servidor: {e}")

# ==========================================
# Inicia a aplicação na porta 5000
# ==========================================
PORTA = 5000
socketserver.TCPServer.allow_reuse_address = True

with socketserver.TCPServer(("", PORTA), ServidorExtrator) as servidor:
    print("="*50)
    print(f" Servidor Web para Lotes ZIP Iniciado com Sucesso!")
    print(f" Acesse pelo navegador: http://127.0.0.1:{PORTA}")
    print("="*50)
    print("Para desligar o servidor, aperte CTRL+C\n")
    servidor.serve_forever()