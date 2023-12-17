from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Tuple, List
from collections import deque
from PIL import Image
import base64
from io import BytesIO
import itertools
import paho.mqtt.client as mqtt

app = FastAPI()

# Configurações MQTT
MQTT_BROKER = "152.67.55.77"
MQTT_PORT = 1883
MQTT_TOPIC = "algorithm-api/topic"

class PathRequest(BaseModel):
    start_point: Tuple[int, int]
    image_base64: str

def find_shortest_path_bfs(
    grid: List[List[int]], start: Tuple[int, int], fixed_end: Tuple[int, int]
) -> List[Tuple[int, int]]:
    rows = len(grid)
    cols = len(grid[0])

    def is_valid(x, y):
        return 0 <= y < rows and 0 <= x < cols and grid[y][x] == 0

    dx = [-1, 1, 0, 0]
    dy = [0, 0, -1, 1]

    dx = [-1, 1, 0, 0, -1, -1, 1, 1]
    dy = [0, 0, -1, 1, -1, 1, -1, 1]

    queue = deque([(start[0], start[1], [])])
    visited = set()

    while queue:
        x, y, path = queue.popleft()
        if (x, y) == fixed_end:
            return path + [(x, y)]

        if (x, y) in visited:
            continue

        visited.add((x, y))

        for add_x, add_y in zip(dx, dy):
            new_x = x + add_x
            new_y = y + add_y

            if is_valid(new_x, new_y):
                queue.append((new_x, new_y, path + [(x, y)]))

    return [] 

def on_connect(client, userdata, flags, rc):
    print(f"Conectado ao broker MQTT com código de retorno: {rc}")

def publish_shortest_path_bfs(chosen_path):
    client = mqtt.Client()
    client.on_connect = on_connect

    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    try:
        client.publish(MQTT_TOPIC, str(chosen_path))
    except Exception as e:
        print(f"Erro ao publicar no tópico MQTT: {str(e)}")

    client.loop_stop()

def png_to_matrix(file_path: str) -> List[List[int]]:
    image = Image.open(file_path).convert("L")
    width, height = image.size
    pixel_values = list(image.getdata())

    matrix = [pixel_values[i * width : (i + 1) * width] for i in range(height)]
    return [[1 if pixel < 128 else 0 for pixel in row] for row in matrix]

def save_matrix_as_png(matrix: List[List[int]], output_path: str) -> None:
    scale = 1
    image = Image.new("RGB", (len(matrix[0]) * scale, len(matrix) * scale), color="white")
    pixels = image.load()

    for y in range(len(matrix)):
        for x in range(len(matrix[0])):
            color = (0, 0, 0)
            if matrix[y][x] == 2:
                color = (255, 0, 0)
            elif matrix[y][x] == 0:
                color = (255, 255, 255)
            for dy, dx in itertools.product(range(scale), range(scale)):
                pixels[x * scale + dx, y * scale + dy] = color

    image.save(output_path)

def enlarge_walls(matrix: List[List[int]], dist: int, value: int = 1) -> List[List[int]]:
    rows = len(matrix)
    cols = len(matrix[0])
    directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]

    new_matrix = [row[:] for row in matrix]

    def expand_walls(x, y):
        for dx, dy in directions:
            for d in range(1, dist + 1):
                new_x, new_y = x + dx * d, y + dy * d
                if 0 <= new_y < rows and 0 <= new_x < cols and matrix[new_y][new_x] == 0:
                    new_matrix[new_y][new_x] = value
                else:
                    break

    for y in range(rows):
        for x in range(cols):
            if matrix[y][x] == value:
                expand_walls(x, y)

    return new_matrix

@app.post("/find_shortest_path")
async def find_shortest_path(request: PathRequest):
    try:
        image_data = base64.b64decode(request.image_base64)
        image = Image.open(BytesIO(image_data))

        temp_image_path = "temp_image.png"
        image.save(temp_image_path)

        map_grid = png_to_matrix(temp_image_path)
        map_grid_enlarged = enlarge_walls(map_grid, 10)

        start_point = request.start_point
        fixed_end_point_1 = (12, 39)
        fixed_end_point_2 = (138, 725)

        shortest_path_1 = find_shortest_path_bfs(map_grid_enlarged, start_point, fixed_end_point_1)
        shortest_path_2 = find_shortest_path_bfs(map_grid_enlarged, start_point, fixed_end_point_2)

        if len(shortest_path_1) > 0 and (len(shortest_path_2) == 0 or len(shortest_path_1) < len(shortest_path_2)):
            print("Caminho mais curto (BFS) para o primeiro ponto final:", shortest_path_1)
            chosen_path = shortest_path_1
        else:
            print("Caminho mais curto (BFS) para o segundo ponto final:", shortest_path_2)
            chosen_path = shortest_path_2

        publish_shortest_path_bfs(chosen_path)

        for x, y in chosen_path:
            map_grid[y][x] = 2
        map_grid = enlarge_walls(map_grid, 2, 2)

        result_image_path = "result_image.png"
        save_matrix_as_png(map_grid, result_image_path)

        with open(result_image_path, "rb") as image_file:
            image_bytes = image_file.read()
            image_base64 = base64.b64encode(image_bytes).decode()

        return {"image_base64": image_base64, "shortest_path_bfs": chosen_path}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ocorreu um erro: {str(e)}")