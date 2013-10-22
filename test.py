from ScrollsSocketClient import ScrollsSocketClient

def run(message):
    print message

# init the scrolls client
scrolls = ScrollsSocketClient()

# subscribe to the SignIn event with function run()
scrolls.subscribe('FirstConnect', run)

# login to the server
scrolls.login()
