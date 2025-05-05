import asyncio
import datetime
import sys
from pathlib import Path

import httpx
from aiofile import AIOFile, Writer
from aiopath import AsyncPath


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
    if input_data[0] != 'exchange': # Перевіряєм чи команда exchange
        return "Це не команда для курсу валют. Використовуйте exchange <кількість днів(за бажанням)> <валюта(за бажанням)>"


    # Визначаємо кількість днів та валюту. Створюжмо наш рядок
    day = int(input_data[1]) if len(input_data) >= 2 else 0
    currency_my = input_data[2] if len(input_data) >= 3 else None

    if day >= 10:
        return r"Вибачте я, як Дорі з Немо - запамятовую не більше 10 днів 0_о"

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
            currency = val.get('currency') # Назва валюти
            purchase_rate = val.get('purchaseRate') # Курс купівлі
            sale_rate = val.get("saleRate") # Курс продажу

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


if __name__ == "__main__":
    print(asyncio.run(get_exchange(sys.argv[1:])))
