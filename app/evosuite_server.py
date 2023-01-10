from app import emitter, utilities, values
from app.uniapr import run_uniapr

import os
from pathlib import Path
from subprocess import PIPE, DEVNULL
import itertools
import socket
import json
import glob
import asyncio
import shutil
import pprint
from collections import defaultdict
import itertools


async def main():
    done = False
    task = None

    def handle_evosuite_message(reader, writer):
        message = await reader.read().decode("utf-8")
        json_data = json.loads(message)
        cmd = json_data["cmd"]
        if cmd == "readJsonFile":
            json_file_path = json_data["data"]["path"]
            with open(json_file_path) as f:
                json_data = json.loads(f.read())
                cmd = json_data["cmd"]

        if cmd == "getPatchPool":
            print('[Server] Sending patch pool.')
            reply = {
                "cmd": "getPatchPool",
                "data": get_patch_pool()
            }
            writer.write(json.dumps(reply).encode("utf-8"))
            await writer.drain()
        elif cmd == 'updateTestPopulation':
            reply_data = update_test_population(json_data)
            reply_file_path = Path("ServerFile0.json").resolve()
            with open(reply_file_path, 'w') as f:
                json.dump(reply_data, f)
            reply = {
                "cmd": "updateTestPopulation",
                "data": {
                    "path": reply_file_path
                }
            }
            writer.write(json.dumps(reply).encode("utf-8"))
            await writer.drain()
        elif cmd == 'getPatchValidationResult':
            print('[Server] Sending patch validation result.')
            test_name = json_data['data']['testId']
            patch_id = json_data['data']['patchId']
            validation_result = get_patch_validation_result(test_name, patch_id)
            reply = {
                "cmd": "getPatchValidationResult",
                "data": {
                    "testId": test_name,
                    "patchId": patch_id,
                    "result": validation_result
                }
            }
            writer.write(json.dumps(reply).encode("utf-8"))
            await writer.drain()
        elif cmd == 'closeConnection':
            print('[Server] Closing connection.')
            writer.close()
            await writer.wait_closed()
            task.cancel()
        else:
            print(f"[Server] Unknown command: {cmd}. Sending back echo.")
            reply = {k: v for k, v in json_data.items()}
            if "data" not in reply:
                reply["data"] = [4, 0, 4]
            writer.write(json.dumps(reply).encode("utf-8"))
            await writer.drain()

    server_socket = socket.socket()
    server_socket.bind(("localhost", 0))
    _, port = server_socket.getsockname()
    server = await asyncio.start_server(handle_evosuite_message, sock=server_socket)
    async with server:
        await server.start_serving()
        # start evosuite here
        evosuite_command = ""

        process = await asyncio.create_subprocess_shell(evosuite_command)

        task = asyncio.create_task(server.serve_forever())
        await server.serve_forever()
    print("interaction done, now tearing down server")


def get_patch_pool():
    return [{"id": i} for i in range(10)]


def update_test_population(json_data):
    population = json_data['data']['generation']
    test_names = json_data['data']['tests']
    classname = json_data['data']['classname']
    test_path = json_data['data']['testSuitePath']
    scaffolding_path = json_data['data']['testScaffoldingPath']

    assert os.path.exists(test_path), test_path
    assert os.path.exists(scaffolding_path), scaffolding_path

    return [population, *test_names, classname]


def get_patch_validation_result(test_name, patch_id):
    if test_name == 'test1' and int(patch_id) == 7:
        validation_result = True
    else:
        validation_result = False

    return validation_result


if __name__ == '__main__':
    asyncio.run(main())
