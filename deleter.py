import requests, re, os, traceback, typing
from datetime import datetime
from time import sleep

#---------------- настрой_очка -----------------#

token = '' # токен вк с доступом к сообщениям
trigger = 'дд' # удаление сообщений
edit_trigger = 'дд-'# редактирует сообщения перед удалением
delete_all_postfix = 'все' # если фразы сверху оканчиваются на эту, удаляются все исходящие сообщения среди последних 200
edit_message = '&#13;' # текст, на который редактируются сообщения
edit_command = False # если True - редактирует сообщение-команду
edit_delay = 0.4 # Задержка между редактированием сообщений (чем больше - тем медленнее сообщения будут редактироваться, ниже шанс капчи (максимальное значение - 2))
doubleslash = True # Если True - сообщения оканчивающиеся на // будут удаляться
stop_phrase = '!ддстоп' # фраза для остановки скрипта, может помочь, если скрипт начал размножаться при перезагрузке хостинга

#-----------------------------------------------#
alive_phrase = f'{trigger}жив'
delete_all_phrase = f'{trigger}{delete_all_postfix}'
edit_as_possible = f'{edit_trigger}{delete_all_postfix}'

logpath = os.path.join(os.path.dirname(__file__), 'deleter.log')

def log(text) -> None:
    with open(logpath, 'a', encoding="utf-8") as f:
        text = datetime.now().strftime("(%H:%M:%S) ") + text
        print(text)
        f.write(f'\n{text}')

def method(m: str, **kwargs) -> dict:
    return requests.post(f'https://api.vk.com/method/{m}?v=5.100&access_token={token}&lang=ru',
        data = kwargs).json()

def get_server() -> typing.Tuple[str, int]:
    s = method('messages.getLongPollServer')
    if 'error' in s.keys():
        log(f'Беды с получением данных для поллинга:\n{s}')
        sleep(5)
        raise Exception(f'Ошибка VK: {s["error"]["error_msg"]}')
    s = s['response']
    return f"http://{s['server']}?act=a_check&key={s['key']}&ts=", s['ts']


exec_url = f'https://api.vk.com/method/execute?v=5.100&access_token={token}&lang=ru'


def delete(update, count = False) -> dict:
    if edit_command:
        method('messages.edit', peer_id = update[3],
                message = edit_message, message_id = update[1])
    if update[5].startswith(alive_phrase):
        return method('messages.send', peer_id = update[3], random_id = 0,
            message = 'жив')
    else:
        if not count:
            count = re.search(r'\d+', update[5])
            if not count:
                if update[5] == delete_all_phrase: count = 200
                else: count = 2
            else: count = int(count[0]) + 1
        code = """
        var i = 0;
        var msg_ids = {};
        var tn = %s;
        var count = %s;
        var pid = %s;
        var items = API.messages.getHistory({"peer_id":pid,"count":200,"offset":0}).items;
        while (count > 0 && i < items.length) {
            if (items[i].out == 1 && items[i].action == null){
                msg_ids.push(items[i].id);
                count = count - 1;
                };
            if ((tn - items[i].date) > 86400) {count = 0;};
            i = i + 1;
        };
        return API.messages.delete({"message_ids": msg_ids,"delete_for_all":"1"});
        """ % (datetime.now().timestamp(), count, update[3])
        return requests.post(exec_url, data = {'code': code}).text


def edit(update) -> dict:
    time = datetime.now().timestamp()
    count = re.search(r'\d+', update[5])
    if not count:
        if update[5] == edit_as_possible:
            count = 1000
        else:
            count = 2
    else:
        count = int(count[0]) + 1
    msg_ids = [str(update[1])]
    for i, cmsg in enumerate(method('messages.getHistory', peer_id = update[3], count = 200)['response']['items']):
        if i == 0 and not edit_command:
            continue
        if time - cmsg['date'] > 86400 or i + 1 == count:
            break
        if cmsg['out'] == 1:
            resp = method('messages.edit', peer_id = update[3],
                message = edit_message, message_id = cmsg['id'])
            msg_ids.append(str(cmsg['id']))
            if resp.get('error'):
                break
            sleep(edit_delay)
    return method('messages.delete', message_ids = ','.join(msg_ids), delete_for_all = 1)

if edit_delay > 2: raise ValueError
lp_url, ts = get_server()
log('Запущено')

while True:
    try:
        data = requests.post(f"{lp_url}{ts}&wait=10&version=3").json()
        if data.get('failed'):
            if data['failed'] == 1:
                data.update({'ts': ts, 'updates': []})
                lp_url = get_server()[0]
            else:
                lp_url, ts = get_server()
                continue
        for update in data['updates']:
            if update[0] == 4 and update[2] & 2:
                update[5] = update[5].lower()
                if update[5].startswith(edit_trigger):
                    log('editing with deleting...\n' + str(edit(update)))
                elif update[5].startswith(trigger):
                    log('deleting...\n' + delete(update))
                elif update[5].endswith('//') and doubleslash:
                    resp = method('messages.delete', message_ids = update[1], delete_for_all = 1)
                    log('doubleslashing...\n' + str(delete(update, 1)))
                elif update[5] == stop_phrase: raise Exception('stop')
        ts = data['ts']
    except Exception as e:
        log(f'Ошиб_очка:\n{traceback.format_exc()}')
        if str(e) == 'stop': break
        ts += 1