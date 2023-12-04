from requests import get
import pandas as pd
from log_pass import api_yandex, password, loggin, tele_token
from pyicloud import PyiCloudService
import math
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
import re
import datetime


dff = pd.DataFrame(columns=['Название', 'Адрес', 'X', 'Y'])
api_key = api_yandex
mag_list = ['Лента', 'Макси', 'Пятерочка', 'Аллея', 'Магнит', 'Золотой Ключ']


def get_magazin(api_key, mag_list):
    for mag in mag_list:
        link = f'https://search-maps.yandex.ru/v1/?text={mag},продукты,Вологда&type=biz&lang=ru_RU&bbox=59.167854,39.815547~59.237225,39.931637&results=50&apikey={api_key}'
        response = get(link)
        mags = response.json()
        for magazin in mags['features']:
            list = [magazin['properties']['name'], magazin['properties']['description'],
                    magazin['geometry']['coordinates'][0], magazin['geometry']['coordinates'][1]]
            print(list)
            dff.loc[len(dff)] = list
    dff[(dff["Название"].str.contains("Мебели") == False) & (dff["Название"].str.contains("Арт-") == False)]
    dff.to_csv('mag_data.csv', index=False)
    return dff

def get_icloud_session(loggin, password):
    api = PyiCloudService(loggin, password)
    if api.requires_2fa:
        print("Two-factor authentication required.")
        code = input("Enter the code you received of one of your approved devices: ")
        result = api.validate_2fa_code(code)
        print("Code validation result: %s" % result)

        if not result:
            print("Failed to verify security code")
            sys.exit(1)

        if not api.is_trusted_session:
            print("Session is not trusted. Requesting trust...")
            result = api.trust_session()
            print("Session trust result %s" % result)

            if not result:
                print("Failed to request trust. You will likely be prompted for the code again in the coming weeks")
    elif api.requires_2sa:
        import click
        print("Two-step authentication required. Your trusted devices are:")

        devices = api.trusted_devices
        for i, device in enumerate(devices):
            print(
                "  %s: %s" % (i, device.get('deviceName',
                                            "SMS to %s" % device.get('phoneNumber')))
            )

        device = click.prompt('Which device would you like to use?', default=0)
        device = devices[device]
        if not api.send_verification_code(device):
            print("Failed to send verification code")
            sys.exit(1)

        code = click.prompt('Please enter validation code')
        if not api.validate_verification_code(device, code):
            print("Failed to verify verification code")
            sys.exit(1)
    return api


def get_location(api):

    latitude_i = api.devices[0].location()['latitude']
    longitude_i = api.devices[0].location()['longitude']

    return latitude_i, longitude_i


def nearer_magazin(latitude_i, longitude_i):
    dff = pd.read_csv('mag_data.csv')

    def dist(llat1, llong1, llat2, llong2):
        rad = 6372795

        # координаты двух точек
        llat1 = llat1
        llong1 = llong1

        llat2 = llat2
        llong2 = llong2

        # в радианах
        lat1 = llat1 * math.pi / 180.
        lat2 = llat2 * math.pi / 180.
        long1 = llong1 * math.pi / 180.
        long2 = llong2 * math.pi / 180.

        # косинусы и синусы широт и разницы долгот
        cl1 = math.cos(lat1)
        cl2 = math.cos(lat2)
        sl1 = math.sin(lat1)
        sl2 = math.sin(lat2)
        delta = long2 - long1
        cdelta = math.cos(delta)
        sdelta = math.sin(delta)

        # вычисления длины большого круга
        y = math.sqrt(math.pow(cl2 * sdelta, 2) + math.pow(cl1 * sl2 - sl1 * cl2 * cdelta, 2))
        x = sl1 * sl2 + cl1 * cl2 * cdelta
        ad = math.atan2(y, x)
        dist = ad * rad

        return dist

    dff['dist'] = dff.apply(lambda x: dist(latitude_i, longitude_i, x.Y, x.X), axis=1)

    min_magazin = list(dff.sort_values('dist').head(1)['Название'])[0]
    min_dist = list(dff.sort_values('dist').head(1)['dist'])[0]

    return min_magazin, min_dist


def write_list(item):
    items = re.split('[,;]+', item)
    shop_list = pd.read_csv('shopping_list.csv')
    len_items = len(items)
    if len(items) == 1:
        shop_list.loc[len(shop_list)] = item
    else:
        for i in items:
            shop_list.loc[len(shop_list)] = i
    shop_list.to_csv('shopping_list.csv', index=False)

    return shop_list, len_items


def del_item(item):
    shop_list = pd.read_csv('shopping_list.csv')
    shop_list = shop_list[shop_list['Товар'] != item]
    shop_list.to_csv('shopping_list.csv', index=False)
    return shop_list

def stop_mess():
    global stop
    stop = 1
    return stop


dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer("Добавь товар")
    print(message.from_user.id)


@dp.message()
async def add_item(message: types.Message) -> None:

    if message.text == 'Ближайший магазин':
        latitude_i, longitude_i = get_location(get_icloud_session(loggin=loggin, password=password))
        min_magazin, min_dist = nearer_magazin(latitude_i, longitude_i)
        await message.answer(f'{min_magazin}, {round(min_dist / 1000, 2)} км')
    elif message.text == 'Хорошо':
        global stop
        stop = stop_mess()
        shop_list = pd.read_csv('shopping_list.csv')
        kb = []
        kb_list = list(shop_list['Товар'])
        for i in kb_list:
            kb.append([types.KeyboardButton(text=i)])
        keyboard = types.ReplyKeyboardMarkup(keyboard=kb)
        await message.answer("Твой список покупок", reply_markup=keyboard)

    else:
        shop_list = pd.read_csv('shopping_list.csv')

        if list(shop_list.loc[shop_list['Товар'] == message.text].count())[0] == 0:
            shop_list, len_items = write_list(message.text)
            if len_items == 1:
                await message.answer(f'Добавлен товар "{message.text}"')
            else:
                await message.answer(f'Добавлены товары "{message.text}"')

        else:
            shop_list = del_item(message.text)
            await message.answer(f'Удален товар "{message.text}"')
        if len(shop_list) == 0:
            await message.answer("Список пуст. Напиши товар чтобы добавить", reply_markup=types.ReplyKeyboardRemove())
        else:
            kb = []
            kb_list = list(shop_list['Товар'])
            for i in kb_list:
                kb.append([types.KeyboardButton(text=i)])
            keyboard = types.ReplyKeyboardMarkup(keyboard=kb)
            await message.answer("Что то ещё?", reply_markup=keyboard)

    print(message.text)


async def main() -> None:
    bot = Bot(tele_token, parse_mode=ParseMode.HTML)
    global stop
    stop = 0
    # await bot.send_message(chat_id=447999564, text='text')
    async def send_not(bot):
        while True:
            global stop
            if stop == 1:
                print('stop')
                await asyncio.sleep(7200)
                stop = 0
            else:
                latitude_i, longitude_i = get_location(get_icloud_session(loggin=loggin, password=password))
                min_magazin, min_dist = nearer_magazin(latitude_i, longitude_i)
                if min_dist < 70:
                    keyboard = types.ReplyKeyboardMarkup(keyboard=[[types.KeyboardButton(text='Хорошо')]])
                    await bot.send_message(chat_id=447999564, text=f'Ты рядом с магазином {min_magazin} посмотри в список',reply_markup=keyboard)
                    print(f'Магазин {min_magazin}')
                else:
                    print(f'Ближайший магазин {min_magazin} {datetime.datetime.now()}')
                await asyncio.sleep(5)
                print('go')

    async def get_mag_evry():
        while True:
            get_magazin(api_key=api_key, mag_list=mag_list)
            print('Магазины обновлены')
            await asyncio.sleep(2678400)

    get_icloud_session(loggin, password)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(dp.start_polling(bot))
        tg.create_task(send_not(bot))
        tg.create_task(get_mag_evry())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
