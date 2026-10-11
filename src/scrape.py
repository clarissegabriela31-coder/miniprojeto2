"""
Etapa 1 — coleta de dados de tabuademares.com/br/paraiba/joao-pessoa.

Objetivo: gravar em data/raw/ os CSVs que as Etapas 2 e 3 vão consumir.

    mares_<ano>.csv      tábua de marés do ano (4 marés por dia)
    mares_previsao.csv   marés do mês corrente, para cruzar com a previsão
    ondas.csv            altura de onda hora a hora (~7 dias à frente)
    vento.csv            velocidade do vento hora a hora (~7 dias à frente)

As funções abaixo estão vazias de propósito. Abra o site no navegador, use o
DevTools para descobrir onde cada dado vive no HTML e implemente o parse.
As colunas de cada CSV são sua decisão — só precisam sustentar as etapas
seguintes (ver README).

Rodar com: uv run python src/scrape.py
"""

import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

# Os imports acima são o ponto de partida: você vai usar todos eles.
# Seu editor pode marcá-los como não usados até você preencher as funções.

URL_BASE = "https://tabuademares.com/br/paraiba/joao-pessoa"
URL_ONDAS = f"{URL_BASE}/previsao/ondas"
URL_VENTO = f"{URL_BASE}/previsao/vento"

# Servidores rejeitam clientes sem User-Agent. Identifique-se.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Segundos de pausa entre requests. Não tire isso.
PAUSA = 1.5

DIR_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def baixar_html(url: str, dados_post: dict | None = None) -> str:

    """Baixa uma página e devolve o HTML.

    Use POST (passando `dados_post`) quando a página só devolver o conteúdo
    que você quer em resposta a um formulário; GET no resto.

    TODO: fazer a requisição com `requests`, checar o status e devolver o texto.
    Dica: `resp.raise_for_status()` falha alto quando o servidor recusa.
    """
    if dados_post:
        resposta = requests.post(url, data=dados_post, headers=HEADERS, timeout=30)
    else:
        resposta = requests.get(url, headers=HEADERS, timeout=30)
    resposta.raise_for_status()
    return resposta.text


def parsear_mares(html: str, ano: int, mes: int) -> list[dict]:
    """Extrai da tábua mensal uma linha por evento de maré.

    Cada dia tem cerca de 4 eventos (duas altas, duas baixas). Além de
    horário e altura, a página traz informação de coeficiente de maré e de
    fase da lua — decida o que vale a pena capturar.

    TODO: localizar a tabela no HTML e percorrer as linhas.
    """
    soup = BeautifulSoup(html, "html.parser")
    eventos = []
    datas_vistas = set()

    for linha in soup.select("tr.tabla_mareas_fila"):
        tag_dia = linha.select_one(".tabla_mareas_dia_numero")
        if tag_dia is None:
            continue # linha sem número de dia (ex.: segunda <tr> do rowspan)

        # Confere se a página é mesmo do mês pedido. Sem isso, um POST errado
        # devolveria o mês atual e as datas sairiam falsas, sem nenhum erro.
        onclick = linha.get("onclick", "") # ex.: Day('2026-10-1')
        if onclick:
            ano_site, mes_site, _ = onclick.split("'")[1].split("-")
            if int(ano_site) != ano or int(mes_site) != mes:
                raise ValueError(f"A página não é de {ano}-{mes:02d}: {onclick}")

        dia = int(tag_dia.get_text(strip=True))
        data = f"{ano}-{mes:02d}-{dia:02d}"

        if data in datas_vistas: #para conferir se aquele dia já foi lido
            continue
        datas_vistas.add(data)

        tag_coef = linha.select_one(".tabla_mareas_coeficiente_numero")
        coeficiente = int(tag_coef.get_text().split()[0])

        for celula in linha.select("td.tabla_mareas_marea"):
            tag_hora = celula.select_one(".tabla_mareas_marea_hora")
            tag_altura = celula.select_one(".tabla_mareas_marea_altura_numero")
            if tag_hora is None or tag_altura is None:
                continue

            eventos.append({
                "data": data,
                "hora": tag_hora.get_text(strip=True),
                "altura_metros": float(tag_altura.get_text(strip=True).replace(",", ".")),
                "tipo": "alta" if celula.select_one(".tabla_mareas_marea_pleamar") else "baixa",
                "coeficiente": coeficiente,
            })

    return eventos


def parsear_previsao(html: str) -> list[dict]:
    # Decidi tirar o ano como parâmetro, pois eu já encontrei a data completa no HTML e não precisei usar.
    """Extrai leituras horárias das páginas de previsão de onda e de vento.

    As duas páginas têm o mesmo layout: um bloco por dia, com uma linha por
    hora dentro. Uma função só deve dar conta das duas.

    TODO: percorrer os blocos de dia e, dentro deles, as linhas de hora.
    Atenção à data: o bloco mostra dia e mês abreviado, sem o ano.
    """
    soup = BeautifulSoup(html, "html.parser")
    leituras = []

    for bloco in soup.select("div.f_cont"):
        link = bloco.select_one("a.a_enlace") #dentro de cada dia tem um link +INFO
        data = link["href"].split("'")[1] #href é o endereço do link = ["javascript:Day(", "2026-10-01", ");"]

        for linha in bloco.select("div.f_temp_horas"):
            partes = linha.select("div.f_temp_hora")
            hora = partes[0].get_text(strip=True)
            direcao = partes[1].get_text(strip=True)

            texto = linha.select_one(".grafico_temp_barra_relleno").get_text(" ", strip=True)
            valor = float(texto.split()[0].replace(",", "."))

            leituras.append({
                "data": data,
                "hora": hora,
                "valor": valor,
                "direcao": direcao,
            })

    return leituras


def coletar_mares_do_ano(ano: int) -> pd.DataFrame:
    """Junta os 12 meses da tábua de marés de `ano` num DataFrame.

    TODO: iterar de janeiro a dezembro, chamar `baixar_html` + `parsear_mares`
    e dormir `PAUSA` entre requisições.
    """
    todos = []
    for  mes in range(1, 13):
        dados_post = {"fecha": f"{ano}-{mes:02d}-01"}
        html = baixar_html(URL_BASE, dados_post)

        eventos = parsear_mares(html, ano, mes)
        print(f"{ano}-{mes:02d}: {len(eventos)} marés")

        todos.extend(eventos)
        time.sleep(PAUSA)
    return pd.DataFrame(todos)


def main(ano: int = 2025) -> None:
    DIR_RAW.mkdir(parents=True, exist_ok=True)
    hoje = datetime.now()

    # TODO: montar os quatro CSVs em DIR_RAW.
    #
    #   1. tábua de marés do ano inteiro   -> mares_{ano}.csv
    #   2. marés do mês corrente           -> mares_previsao.csv
    #   3. previsão de ondas               -> ondas.csv
    #   4. previsão de vento               -> vento.csv
    #
    # Imprima quantas linhas cada arquivo recebeu: um CSV vazio é o erro mais
    # comum e o mais silencioso.

    # 1. tábua das marés do ano inteiro
    df_ano = coletar_mares_do_ano(ano)
    df_ano.to_csv(DIR_RAW / f"mares_{ano}.csv", index=False)
    print(f"mares_{ano}.csv: {len(df_ano)} linhas")

    # 2. marés do mês corrente (GET sem dados o site mostra o mês atual)
    html_mes = baixar_html(URL_BASE)
    df_mes = pd.DataFrame(parsear_mares(html_mes, hoje.year, hoje.month))
    df_mes.to_csv(DIR_RAW / "mares_previsao.csv", index=False)
    print(f"mares_previsao.csv: {len(df_mes)} linhas") 

    # 3. previsão de ondas 
    html_ondas = baixar_html(URL_ONDAS)
    df_ondas = pd.DataFrame(parsear_previsao(html_ondas)).rename(columns={"valor": "altura_m"})
    df_ondas.to_csv(DIR_RAW / "ondas.csv", index=False)
    print(f"ondas.csv: {len(df_ondas)} linhas")
    time.sleep(PAUSA)

    # 4. previsão de vento
    html_vento = baixar_html(URL_VENTO)
    df_vento = pd.DataFrame(parsear_previsao(html_vento)).rename(columns={"valor": "velocidade_km"})
    df_ondas.to_csv(DIR_RAW / "vento.csv", index=False)
    print(f"vento.csv: {len(df_vento)} linhas")

  
if __name__ == "__main__":
    main()
