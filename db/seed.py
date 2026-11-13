"""Cria as tabelas e popula o banco com dados fictícios de vendas.

Uso (na raiz do projeto):
    uv run python db/seed.py

Roda quantas vezes quiser: apaga e recria os dados (TRUNCATE) com a mesma semente,
então o resultado é sempre o mesmo.
"""

import os
import random
from datetime import date, timedelta
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"

# (produto_id, nome, categoria, marca, preço, estoque, descrição)
PRODUTOS = [
    ("P001", "Notebook Dell Inspiron", "Informática", "Dell", 4299.90, 18, "Notebook com processador Intel Core i7, 16 GB de RAM e SSD de 512 GB para uso profissional."),
    ("P002", "Mouse Logitech M170", "Periféricos", "Logitech", 89.90, 120, "Mouse sem fio compacto com receptor USB e pilha de longa duração."),
    ("P003", "Monitor LG 24 polegadas", "Informática", "LG", 899.90, 35, "Monitor Full HD de 24 polegadas com painel IPS e entrada HDMI."),
    ("P004", "Teclado Mecânico Redragon", "Periféricos", "Redragon", 249.90, 60, "Teclado mecânico com switches azuis e iluminação RGB."),
    ("P005", "Notebook Lenovo IdeaPad", "Informática", "Lenovo", 3899.90, 22, "Notebook com Ryzen 5, 8 GB de RAM e SSD de 256 GB para o dia a dia."),
    ("P006", "Headset HyperX Cloud Stinger", "Periféricos", "HyperX", 349.90, 45, "Headset gamer leve com microfone articulado e almofadas de espuma."),
    ("P007", "SSD Kingston 480GB", "Armazenamento", "Kingston", 299.90, 90, "SSD SATA de 480 GB para acelerar notebooks e desktops."),
    ("P008", "Webcam Logitech C920", "Periféricos", "Logitech", 499.90, 40, "Webcam Full HD com microfone estéreo para reuniões e transmissões."),
    ("P009", "Impressora HP DeskJet", "Impressão", "HP", 749.90, 25, "Impressora multifuncional jato de tinta com Wi-Fi."),
    ("P010", "Cadeira Gamer ThunderX3", "Móveis", "ThunderX3", 1299.90, 15, "Cadeira ergonômica com apoio lombar e braços ajustáveis."),
    ("P011", "Roteador TP-Link Archer", "Redes", "TP-Link", 399.90, 55, "Roteador Wi-Fi 6 de banda dupla para casas e escritórios pequenos."),
    ("P012", "MacBook Air M1", "Informática", "Apple", 6999.90, 10, "Notebook ultrafino com chip M1, 8 GB de memória e bateria de longa duração."),
    ("P013", "Cabo HDMI 2 metros", "Acessórios", "Multilaser", 39.90, 300, "Cabo HDMI 2.0 de 2 metros com suporte a 4K."),
    ("P014", "Tablet Samsung Galaxy Tab", "Mobile", "Samsung", 2199.90, 20, "Tablet de 10,5 polegadas com 128 GB e caneta S Pen."),
    ("P015", "Smartphone Motorola Edge", "Mobile", "Motorola", 2499.90, 30, "Smartphone 5G com tela OLED de 144 Hz e câmera de 50 MP."),
    ("P016", "Nobreak SMS 1200VA", "Energia", "SMS", 699.90, 28, "Nobreak de 1200 VA com autonomia para proteger computadores e roteadores."),
    ("P017", "Placa de Vídeo RTX 4060", "Hardware", "Asus", 2199.90, 12, "Placa de vídeo com 8 GB GDDR6 para jogos em Full HD e edição."),
    ("P018", "Memória RAM Kingston 16GB", "Hardware", "Kingston", 299.90, 80, "Memória DDR4 de 16 GB, 3200 MHz, para desktop."),
    ("P019", "Licença Windows 11 Pro", "Software", "Microsoft", 899.90, 200, "Licença digital do Windows 11 Pro para uma máquina."),
    ("P020", "Notebook Acer Aspire 5", "Informática", "Acer", 3499.90, 17, "Notebook com Intel Core i5, 8 GB de RAM e tela Full HD de 15,6 polegadas."),
    ("P021", "Monitor Samsung 27 polegadas", "Informática", "Samsung", 1399.90, 26, "Monitor curvo de 27 polegadas com taxa de atualização de 75 Hz."),
    ("P022", "Mouse Gamer Logitech G203", "Periféricos", "Logitech", 159.90, 70, "Mouse gamer com sensor de 8000 DPI e iluminação RGB."),
    ("P023", "Teclado Sem Fio Logitech K380", "Periféricos", "Logitech", 299.90, 50, "Teclado Bluetooth compacto que conecta em até três dispositivos."),
    ("P024", "SSD NVMe Kingston 1TB", "Armazenamento", "Kingston", 549.90, 64, "SSD NVMe de 1 TB com leitura de até 3500 MB/s."),
    ("P025", "HD Externo Seagate 2TB", "Armazenamento", "Seagate", 449.90, 48, "HD externo portátil de 2 TB com conexão USB 3.0."),
    ("P026", "Pen Drive SanDisk 64GB", "Armazenamento", "SanDisk", 49.90, 250, "Pen drive USB 3.0 de 64 GB."),
    ("P027", "Impressora Epson EcoTank L3250", "Impressão", "Epson", 1099.90, 19, "Impressora com tanque de tinta de alto rendimento e Wi-Fi."),
    ("P028", "Cartucho de Tinta HP 664", "Impressão", "HP", 79.90, 140, "Cartucho preto original compatível com a linha DeskJet."),
    ("P029", "Switch TP-Link 8 portas", "Redes", "TP-Link", 189.90, 42, "Switch Gigabit não gerenciável com 8 portas."),
    ("P030", "Access Point Ubiquiti UniFi U6", "Redes", "Ubiquiti", 1199.90, 14, "Access point Wi-Fi 6 para ambientes corporativos."),
    ("P031", "Smartphone Samsung Galaxy S24", "Mobile", "Samsung", 4299.90, 16, "Smartphone topo de linha com 256 GB e câmera tripla."),
    ("P032", "iPhone 15", "Mobile", "Apple", 5499.90, 13, "Smartphone com 128 GB, tela Super Retina e conector USB-C."),
    ("P033", "Carregador Turbo USB-C 65W", "Acessórios", "Anker", 199.90, 110, "Carregador rápido de 65 W para notebooks e celulares."),
    ("P034", "Mochila para Notebook 15,6 pol", "Acessórios", "Targus", 179.90, 75, "Mochila resistente à água com compartimento acolchoado para notebook."),
    ("P035", "Hub USB-C 7 em 1", "Acessórios", "Anker", 289.90, 58, "Hub com HDMI, USB-A, leitor de cartão e entrada de energia."),
    ("P036", "Mesa para Computador", "Móveis", "Madesa", 649.90, 21, "Mesa de escritório com gaveta e suporte para teclado."),
    ("P037", "Placa de Vídeo RTX 4070", "Hardware", "Gigabyte", 4399.90, 8, "Placa de vídeo com 12 GB GDDR6X para jogos em QHD."),
    ("P038", "Processador Ryzen 5 5600", "Hardware", "AMD", 799.90, 33, "Processador de 6 núcleos e 12 threads para o soquete AM4."),
    ("P039", "Licença Microsoft Office 365", "Software", "Microsoft", 449.90, 180, "Assinatura anual do pacote Office com Word, Excel e PowerPoint."),
    ("P040", "Antivírus Kaspersky 1 ano", "Software", "Kaspersky", 129.90, 220, "Licença de um ano de antivírus para um dispositivo."),
]

# (vendedor_id, nome, email, região, cargo, admissão, meta mensal)
VENDEDORES = [
    ("V001", "Ana Souza", "ana.souza@loja-exemplo.com.br", "Sudeste", "Gerente de Contas", date(2021, 3, 15), 45000.00),
    ("V002", "Carlos Lima", "carlos.lima@loja-exemplo.com.br", "Sul", "Vendedor Sênior", date(2022, 7, 4), 38000.00),
    ("V003", "Mariana Alves", "mariana.alves@loja-exemplo.com.br", "Nordeste", "Vendedor Pleno", date(2023, 1, 9), 30000.00),
    ("V004", "João Pereira", "joao.pereira@loja-exemplo.com.br", "Centro-Oeste", "Vendedor Pleno", date(2023, 5, 22), 28000.00),
    ("V005", "Fernanda Rocha", "fernanda.rocha@loja-exemplo.com.br", "Sudeste", "Vendedor Sênior", date(2020, 11, 30), 42000.00),
    ("V006", "Rafael Martins", "rafael.martins@loja-exemplo.com.br", "Norte", "Vendedor Júnior", date(2024, 2, 12), 22000.00),
    ("V007", "Beatriz Moreira", "beatriz.moreira@loja-exemplo.com.br", "Sul", "Vendedor Pleno", date(2023, 9, 18), 31000.00),
    ("V008", "Lucas Ferreira", "lucas.ferreira@loja-exemplo.com.br", "Nordeste", "Vendedor Júnior", date(2024, 6, 3), 20000.00),
    ("V009", "Camila Duarte", "camila.duarte@loja-exemplo.com.br", "Centro-Oeste", "Vendedor Sênior", date(2021, 8, 25), 36000.00),
    ("V010", "Pedro Nogueira", "pedro.nogueira@loja-exemplo.com.br", "Norte", "Vendedor Pleno", date(2022, 12, 5), 27000.00),
]

# As 20 primeiras vendas são as do CSV original: (venda_id, data, produto, vendedor, quantidade)
VENDAS_ORIGINAIS = [
    (1, date(2026, 1, 5), "P001", "V001", 1),
    (2, date(2026, 1, 6), "P002", "V002", 3),
    (3, date(2026, 1, 7), "P003", "V001", 2),
    (4, date(2026, 1, 8), "P004", "V003", 1),
    (5, date(2026, 1, 9), "P005", "V002", 1),
    (6, date(2026, 1, 10), "P001", "V003", 2),
    (7, date(2026, 1, 11), "P006", "V004", 2),
    (8, date(2026, 1, 12), "P007", "V005", 4),
    (9, date(2026, 1, 13), "P008", "V001", 1),
    (10, date(2026, 1, 14), "P009", "V006", 1),
    (11, date(2026, 1, 15), "P010", "V003", 1),
    (12, date(2026, 1, 16), "P011", "V004", 2),
    (13, date(2026, 1, 17), "P012", "V005", 1),
    (14, date(2026, 1, 18), "P013", "V002", 5),
    (15, date(2026, 1, 19), "P014", "V006", 1),
    (16, date(2026, 1, 20), "P015", "V001", 2),
    (17, date(2026, 1, 21), "P016", "V004", 1),
    (18, date(2026, 1, 22), "P017", "V005", 1),
    (19, date(2026, 1, 23), "P018", "V003", 3),
    (20, date(2026, 1, 24), "P019", "V002", 2),
]

TOTAL_VENDAS = 500
FORMAS_PAGAMENTO = ["Cartão de crédito", "Pix", "Boleto", "Cartão de débito"]


def gerar_vendas() -> list[tuple]:
    """Gera vendas fixas (semente 42): as 20 originais mais as demais."""
    rng = random.Random(42)
    preco = {produto[0]: produto[4] for produto in PRODUTOS}
    ids_produtos = [produto[0] for produto in PRODUTOS]
    # Produtos baratos vendem mais vezes que os caros.
    pesos = [1 / preco[produto_id] ** 0.5 for produto_id in ids_produtos]
    ids_vendedores = [vendedor[0] for vendedor in VENDEDORES]

    vendas = []
    for venda_id, data_venda, produto_id, vendedor_id, quantidade in VENDAS_ORIGINAIS:
        valor = round(preco[produto_id] * quantidade, 2)
        pagamento = FORMAS_PAGAMENTO[venda_id % len(FORMAS_PAGAMENTO)]
        vendas.append((venda_id, data_venda, produto_id, vendedor_id, quantidade, preco[produto_id], valor, pagamento, "Concluída"))

    inicio = date(2026, 1, 25)
    dias = (date(2026, 9, 30) - inicio).days
    datas = sorted(inicio + timedelta(days=rng.randint(0, dias)) for _ in range(TOTAL_VENDAS - len(vendas)))

    for venda_id, data_venda in enumerate(datas, start=len(vendas) + 1):
        produto_id = rng.choices(ids_produtos, weights=pesos)[0]
        quantidade = rng.randint(1, 5) if preco[produto_id] < 300 else rng.randint(1, 2)
        valor = round(preco[produto_id] * quantidade, 2)
        status = rng.choices(["Concluída", "Pendente", "Cancelada"], weights=[90, 6, 4])[0]
        vendas.append((venda_id, data_venda, produto_id, rng.choice(ids_vendedores), quantidade, preco[produto_id], valor, rng.choice(FORMAS_PAGAMENTO), status))

    return vendas


def main() -> None:
    _ = load_dotenv(BASE_DIR / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("Defina DATABASE_URL no arquivo .env.")

    vendas = gerar_vendas()

    with psycopg2.connect(database_url) as conexao, conexao.cursor() as cursor:
        cursor.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        cursor.execute("TRUNCATE vendas, produtos, vendedores")
        cursor.executemany(
            "INSERT INTO produtos (produto_id, nome, categoria, marca, preco_unitario, estoque, descricao) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            PRODUTOS,
        )
        cursor.executemany(
            "INSERT INTO vendedores (vendedor_id, nome, email, regiao, cargo, data_admissao, meta_mensal) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            VENDEDORES,
        )
        cursor.executemany(
            "INSERT INTO vendas (venda_id, data_venda, produto_id, vendedor_id, quantidade, "
            "preco_unitario, valor_total, forma_pagamento, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            vendas,
        )

    print(f"Banco populado: {len(PRODUTOS)} produtos, {len(VENDEDORES)} vendedores, {len(vendas)} vendas.")


if __name__ == "__main__":
    main()
