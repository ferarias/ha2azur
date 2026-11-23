import asyncio
import getpass
import serialx
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

async def recibir(reader):
    while True:
        data = await reader.read(1024)
        if not data:
            print("\nConexión cerrada por el dispositivo.")
            return
        print(f"\nRX texto: {data!r}")
        print(f"RX hex:   {data.hex(' ')}")


async def main():
    host = input("IP o nombre del AUX-2: ").strip()
    key = getpass.getpass(
        "Clave de cifrado ESPHome (Enter si no utiliza cifrado): "
    ).strip()

    options = {}
    if key:
        options["key"] = key

    url = (
        f"esphome://{host}:6053/"
        "?port_name=RS-232+Port+1"
    )

    print("Conectando al puerto 1...")

    reader, writer = await serialx.open_serial_connection(
        url=url,
        baudrate=9600,
        bytesize=8,
        parity="N",
        stopbits=1,
        **options,
    )

    print("Conectado: 9600, 8N1.")
    print("Escribe un comando ASCII y pulsa Enter.")
    print("Se añadirá automáticamente un retorno de carro (CR).")
    print("Escribe /salir para terminar.")

    session = PromptSession()
    receiver = asyncio.create_task(recibir(reader))

    try:
        while True:
            with patch_stdout():
                command = await session.prompt_async("TX> ")


            if command.strip().lower() == "/salir":
                break

            if not command:
                continue

            payload = command.encode("ascii") + b"\r"
            print(f"TX bytes: {payload!r}")
            writer.write(payload)
            await writer.drain()
    finally:
        receiver.cancel()
        await asyncio.gather(receiver, return_exceptions=True)
        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"\nERROR: {type(exc).__name__}: {exc}")