import datetime
import pytz

from traffic_scanner.bot_controller import dp, bc, updater


datetime.datetime.now(tz=pytz.timezone('Europe/Moscow'))
print(datetime.datetime.now())

dp.run_async(bc.td.serve)
updater.start_polling()
updater.idle()
