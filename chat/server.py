import asyncio
import logging
import datetime
from pathlib import Path

import httpx
import websockets
import names
from websockets import WebSocketServerProtocol
from websockets.exceptions import ConnectionClosedOK
from aiofile import AIOFile, Writer
from aiopath import AsyncPath

logging.basicConfig(level=logging.INFO)


async def request(url: str) -> dict | str:
    async with httpx.AsyncClient() as client: # Створюємо клієнта
        r = await client.get(url) # Виконуємо запит
        if r.status_code == 200: # Ок чи не ок
            result = r.json() # Парсимо
            return result
        else:
            return "Не вийшло в мене взнати курс. Приват не відповідає :)"


async def log_exchange_command(day, currency):
    base_dir = Path(__file__).parent # Поточна папка
    log_path = AsyncPath(base_dir / "exchange.log") # Шлях логу
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") # Дата
    log_msg = f"[{now}] Виконано команду exchange | Днів: {day} | Валюта: {currency}\n"

    async with AIOFile(log_path, 'a') as afp: # Відкриваємо файл асинхронно
        writer = Writer(afp) # Створюємо записувач
        await writer(log_msg) # Записуємо в файл
        await afp.fsync() # Синхронізуємо файл


async def get_exchange(input_data: list):
    # Визначаємо кількість днів та валюту. Створюжмо наш рядок
    day = int(input_data[0]) if len(input_data) >= 1 else 0
    currency_my = input_data[1] if len(input_data) >= 2 else None
    list_data = ''
    # Логування просте як дошка
    await log_exchange_command(day, currency_my)

    # Якщо день 0 то йдем на поточне АПІ
    if day == 0:
        response = await request(f'https://api.privatbank.ua/p24api/pubinfo?exchange&coursid=5')
        for val in response:
            list_data += (
                f"Купівля {val.get('ccy')}: {float(val.get('buy')):.2f} грн.\nПродаж  {val.get('ccy')}: {float(val.get('sale')):.2f} грн. \n\n")
        return list_data

    # Створюємо список корутин і дати запитів (дати не дуже потрібні але для краси хай буде)
    tasks = []
    date_url = []
    for i in range(day):
        date = datetime.datetime.now() - datetime.timedelta(days=i)
        date_str = date.strftime('%d.%m.%Y')
        tasks.append(asyncio.create_task(
            request(f'https://api.privatbank.ua/p24api/exchange_rates?date={date_str}')))
        date_url.append(date_str)

    # Випускаємо гадзера
    responses = await asyncio.gather(*tasks)

    # Звичайна обробка даних яку бажано викинути в окрему функцію
    for current_date, response in zip(date_url, responses):

        # Якщо немає даних то виводимо що їх немає
        if not response or "exchangeRate" not in response:
            list_data += f"Нема даних за {current_date}\n\n"
            continue

        # Якщо дані є то опрацьовуємо їх
        list_data += (f"{'-' * 30}\n\nКурс валют на {current_date}\n\n")

        # Прапорець на те що валюта не знайдена
        matched = False

        # Наш головний цикл обробки даних
        for val in response.get("exchangeRate", []):
            currency = val.get('currency')  # Назва валюти
            purchase_rate = val.get('purchaseRate')  # Курс купівлі
            sale_rate = val.get("saleRate")  # Курс продажу

            if not (currency and purchase_rate and sale_rate):
                continue

            if currency_my:
                if currency == currency_my:
                    list_data += (
                        f"Купівля {currency}: {purchase_rate:.2f} грн.\n"
                        f"Продаж {currency}: {sale_rate:.2f} грн.\n\n"
                    )
                    matched = True
            else:
                list_data += (
                    f"Купівля {currency}: {purchase_rate:.2f} грн.\n"
                    f"Продаж {currency}: {sale_rate:.2f} грн.\n\n"
                )

        if currency_my and not matched:
            list_data += f"Немає валюти з назвою {currency_my}\n"
    return list_data


class Server:
    clients = set()  # Список клієнтів

    async def register(self, ws: WebSocketServerProtocol):  # Реєструємо клієнта
        ws.name = names.get_full_name()  # Генератор імені
        self.clients.add(ws)  # Додаємо клієнта в список
        logging.info(f'{ws.remote_address} connects')

    async def unregister(self, ws: WebSocketServerProtocol):  # Видаляємо клієнта
        self.clients.remove(ws)
        logging.info(f'{ws.remote_address} disconnects')

    async def send_to_clients(self, message: str):  # Відправляємо повідомлення всім клієнтам
        if self.clients:
            [await client.send(message) for client in self.clients]

    async def ws_handler(self, ws: WebSocketServerProtocol):  # Основна функція обробки запитів
        await self.register(ws)  # Реєструємо клієнта
        try:
            await self.distrubute(ws)  # Обробка запита
        except ConnectionClosedOK:  # якщо закрито зєднання то пас
            pass
        finally:
            await self.unregister(ws)  # видаляємо клієнта

    async def distrubute(self, ws: WebSocketServerProtocol):  # Обробник запитів
        async for message in ws:  # Отримуємо повідомлення від клієнта
            spl_message = message.split()  # Парсимо повідомлення
            if spl_message[0].lower() == "exchange":  # якщо перше слово exchange то виводимо курс валют
                exchange = await get_exchange(spl_message[1:])  # отримуємо курс
                await self.send_to_clients(exchange)  # відправляємо його всім
            else:
                await self.send_to_clients(
                    f"{ws.name}: {message}")  # відправляємо всім повідомлення де ws.name - імя а message - текст


async def main():
    # Ніц цікавого просто запуск сервера
    server = Server()
    async with websockets.serve(server.ws_handler, 'localhost', 8080):
        await asyncio.Future()  # run forever


if __name__ == '__main__':
    asyncio.run(main())
