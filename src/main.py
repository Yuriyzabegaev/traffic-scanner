from traffic_scanner.bot_controller import dp, bc, updater

dp.run_async(bc.td.serve)
updater.start_polling()
updater.idle()

# import datetime
# print(datetime.datetime.now())