import json
import sys
import os

# Credenciais do servidor
SERVER = "http://testeeng.com:80"
USERNAME = "938915698"
PASSWORD = "H788v6338E"

def process_json_file(json_file, playlist_lines):
    """
    Processa um JSON e adiciona ao playlist_lines
    """
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        print(f"❌ Erro ao ler {json_file}: {e}")
        return

    for item in items:
        name = item.get("name", "Sem Nome")
        icon = item.get("stream_icon", "")
        stream_type = item.get("stream_type", "live")  # será usado como group-title

        # Definir URL de acordo com o tipo
        if stream_type == "live":
            stream_id = item.get("stream_id")
            url = f"{SERVER}/live/{USERNAME}/{PASSWORD}/{stream_id}.ts"
        elif stream_type == "movie":
            stream_id = item.get("stream_id")
            url = f"{SERVER}/movie/{USERNAME}/{PASSWORD}/{stream_id}.mp4"
        elif stream_type == "series":
            series_id = item.get("series_id")
            url = f"{SERVER}/series/{USERNAME}/{PASSWORD}/{series_id}.mp4"
        else:
            # Caso desconhecido
            continue

        # Adicionar ao playlist com group-title = stream_type
        extinf = f'#EXTINF:-1 tvg-id="{stream_id}" tvg-logo="{icon}" group-title="{stream_type}",{name}'
        playlist_lines.append(extinf)
        playlist_lines.append(url)

def main():
    if len(sys.argv) < 2:
        print("Uso: python gerar_playlist_cli.py arquivo1.json [arquivo2.json ...]")
        sys.exit(1)

    json_files = sys.argv[1:]
    playlist_lines = ["#EXTM3U"]

    for json_file in json_files:
        if not os.path.isfile(json_file):
            print(f"❌ Arquivo não encontrado: {json_file}")
            continue
        print(f"🔹 Processando {json_file}...")
        process_json_file(json_file, playlist_lines)

    output_file = "playlist_completa.m3u8"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(playlist_lines))

    print(f"\n✅ Playlist gerada com sucesso: {output_file}")

if __name__ == "__main__":
    main()
