#!/usr/bin/env python

import sys

from purchase_bot import PurchaseBot


def main():
    debug = len(sys.argv) == 2 and sys.argv[1] == "--debug"

    bot = PurchaseBot(debug=debug)
    bot.main()


if __name__ == '__main__':
    main()
