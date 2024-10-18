import requests
import asyncio
import websockets
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Константы
STARTING_CAPITAL = 100
GRID_SIZE = 10
PART_CAPITAL = STARTING_CAPITAL / GRID_SIZE
ASSET_LIST = ['BTC', 'ETH', 'BNB', 'XRP', 'ADA', 'SOL', 'DOT', 'DOGE', 'LTC', 'LINK']
BUY_THRESHOLD = 0.02  # 2% для покупки
SELL_THRESHOLD = 0.02  # 2% для продажи

# Глобальные переменные
portfolio = {}
account_balance = STARTING_CAPITAL


# Асинхронная функция для получения текущей цены через WebSocket
async def price_stream(symbol, callback):
    url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@ticker"
    async with websockets.connect(url) as websocket:
        while True:
            response = await websocket.recv()
            data = json.loads(response)
            current_price = float(data['c'])  # 'c' - это текущая цена
            await callback(symbol, current_price)


# Функция обратного вызова для обновления портфеля
async def update_portfolio(symbol, current_price):
    global account_balance
    if symbol in portfolio:
        buy_price = portfolio[symbol]['buy_price']

        # Логика покупки
        if portfolio[symbol]['amount'] == 0:  # Если еще не купили актив
            if (buy_price - current_price) / buy_price >= BUY_THRESHOLD:  # Условие покупки
                amount_to_buy = PART_CAPITAL / current_price
                portfolio[symbol]['amount'] += amount_to_buy
                account_balance -= PART_CAPITAL
                print(f"Куплено {amount_to_buy:.4f} {symbol}. Текущий баланс: ${account_balance:.2f}")

        # Логика продажи
        elif (current_price - buy_price) / buy_price >= SELL_THRESHOLD:  # Условие продажи
            account_balance += portfolio[symbol]['amount'] * current_price
            print(f"Продано {portfolio[symbol]['amount']:.4f} {symbol}. Текущий баланс: ${account_balance:.2f}")
            portfolio[symbol]['amount'] = 0


# Функция получения цены через REST API (на случай проблем с WebSocket)
def get_current_price(asset):
    url = f'https://api1.binance.com/api/v3/ticker/price?symbol={asset}USDT'  # Используем другой сервер
    try:
        response = requests.get(url)
        response.raise_for_status()  # Проверка на успешный ответ
        data = response.json()

        if 'price' in data:
            return float(data['price'])
        else:
            print(f"Ошибка: В ответе API отсутствует ключ 'price' для актива {asset}.")
            return None
    except requests.exceptions.HTTPError as e:
        print(f"HTTP ошибка при запросе цены актива {asset}: {e}")
        return None
    except Exception as e:
        print(f"Ошибка при получении цены актива {asset}: {e}")
        return None


# Обработка команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Добро пожаловать в торгового бота!\nВыберите актив (можно до 3): " + ', '.join(ASSET_LIST))

# Обработка команды /select
async def select_asset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) == 0:  # Проверяем, передан ли аргумент
        await update.message.reply_text("Пожалуйста, укажите актив для выбора. Пример: /select BTC ETH ADA.")
        return

    # Ограничиваем выбор до 3 активов
    if len(context.args) > 3:
        await update.message.reply_text("Вы можете выбрать только до 3 активов одновременно.")
        return

    selected_assets = []
    for asset in context.args:
        asset = asset.upper()
        if asset in ASSET_LIST:
            selected_assets.append(asset)
            portfolio[asset] = {'buy_price': None, 'amount': 0}  # Инициализируем портфель
        else:
            await update.message.reply_text(f"Неверный актив: {asset}. Пожалуйста, выберите из: " + ', '.join(ASSET_LIST))

    if selected_assets:
        await update.message.reply_text(f"Вы выбрали активы: {', '.join(selected_assets)}.")
    else:
        await update.message.reply_text("Не выбрано ни одного корректного актива.")

# Обработка команды /show
async def show_selected_assets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not portfolio:
        await update.message.reply_text("Вы еще не выбрали ни одного актива.")
        return

    selected_assets = ', '.join(portfolio.keys())
    await update.message.reply_text(f"Выбранные активы: {selected_assets}")

# Обработка команды /remove
async def remove_asset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) == 0:  # Проверяем, передан ли аргумент
        await update.message.reply_text("Пожалуйста, укажите актив для удаления. Пример: /remove BTC.")
        return

    removed_assets = []
    for asset in context.args:
        asset = asset.upper()
        if asset in portfolio:
            del portfolio[asset]  # Удаляем актив из портфеля
            removed_assets.append(asset)
        else:
            await update.message.reply_text(f"Актив {asset} не найден в вашем портфеле.")

    if removed_assets:
        await update.message.reply_text(f"Удалены активы: {', '.join(removed_assets)}.")
    else:
        await update.message.reply_text("Не удалено ни одного корректного актива.")

# Логика торговли
async def trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global account_balance
    print(f"Текущий баланс перед торговлей: ${account_balance:.2f}")  # Проверяем начальный баланс

    for asset in portfolio:
        current_price = get_current_price(asset)

        if current_price is None:
            print(f"Не удалось получить цену для {asset}. Пропускаем актив.")
            continue

        previous_price = portfolio[asset].get('previous_price', current_price)  # Используем предыдущую цену или текущую
        portfolio[asset]['previous_price'] = current_price  # Обновляем предыдущую цену на текущую

        if current_price < previous_price:
            account_balance -= 10  # Уменьшаем счет на $10, если цена упала
            print(f"Цена {asset} упала. Уменьшаем счет на $10.")
            await update.message.reply_text(f"🔻 Цена {asset} упала до ${current_price:.2f}. Счет уменьшен на $10.")
        elif current_price > previous_price:
            account_balance += 10  # Увеличиваем счет на $10, если цена выросла
            print(f"Цена {asset} повысилась. Увеличиваем счет на $10.")
            await update.message.reply_text(f"🔺 Цена {asset} повысилась до ${current_price:.2f}. Счет увеличен на $10.")

    # Вывод состояния счета после каждой сделки
    await update.message.reply_text(f"💼 Состояние счета: ${account_balance:.2f}")
    print(f"Окончательный баланс после торговли: ${account_balance:.2f}")  # Финальный вывод баланса

def main() -> None:
    # Создаем Application и передаем ему токен вашего бота
    application = ApplicationBuilder().token("ВАШ ТОКЕН ТГ").build()

    # Обрабатываем команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("select", select_asset))
    application.add_handler(CommandHandler("trade", trade))
    application.add_handler(CommandHandler("show", show_selected_assets))
    application.add_handler(CommandHandler("remove", remove_asset))

    # Запускаем бота
    application.run_polling()


if __name__ == '__main__':
    main()
