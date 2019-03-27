# -*- coding: utf-8 -*-

from nose.tools import eq_

from purchase_bot.bot import get_request_id, VALID_ID_RANGE


def test_get_request_id():
    ids, msg = get_request_id('承認 1-3')
    eq_(ids, [1, 2, 3])
    eq_(msg, '')

    ids, msg = get_request_id('承認 1-3 5-9')
    eq_(ids, [1, 2, 3, 5, 6, 7, 8, 9])
    eq_(msg, '')

    ids, msg = get_request_id('承認 1-3 5-7 7-9')
    eq_(ids, [1, 2, 3, 5, 6, 7, 8, 9])
    eq_(msg, '')

    ids, msg = get_request_id('承認 1 2-3 4 5-7 8 9')
    eq_(ids, [1, 2, 3, 4, 5, 6, 7, 8, 9])
    eq_(msg, '')

    ids, msg = get_request_id('承認 -1-2')
    eq_(ids, [])
    eq_(msg, 'WRONG_REQUEST {} : 0より小さいIDを使っている可能性があります。\n'.format('-1-2'))

    ids, msg = get_request_id('承認 -1')
    eq_(ids, [])
    eq_(msg, 'WRONG_REQUEST {} : 0以上の半角数字以外が含まれています。\n'.format('-1'))

    ids, msg = get_request_id('承認 -1 -1-2')
    eq_(ids, [])
    eq_(msg, 'WRONG_REQUEST {} : 0以上の半角数字以外が含まれています。\n'.format('-1') +
        'WRONG_REQUEST {} : 0より小さいIDを使っている可能性があります。\n'.format('-1-2'))

    ids, msg = get_request_id('承認 a-2')
    eq_(ids, [])
    eq_(msg, 'WRONG_REQUEST {} : 0以上の半角数字以外が含まれています。\n'.format('a-2'))

    ids, msg = get_request_id('承認 a')
    eq_(ids, [])
    eq_(msg, 'WRONG_REQUEST {}: IDは整数でなければなりません。\n'.format('a'))

    ids, msg = get_request_id('承認 2-1')
    eq_(ids, [])
    eq_(msg, 'WRONG_REQUEST 2-1 : ID1-ID2では、ID1はID2以下である必要があります。\n')

    ids, msg = get_request_id('承認 1-100')
    eq_(ids, [])
    eq_(msg, 'WRONG_REQUEST 1-100 : 一度に{}個より多くのIDは選択できません。\n'.format(VALID_ID_RANGE))
