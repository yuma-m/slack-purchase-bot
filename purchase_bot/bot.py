"""
購入申請管理ボット
"""

import datetime
import logging
import os
import time
import unicodedata

from slackclient import SlackClient

from .model import PurchaseRequest
from .repo import PurchaseRepo

USAGE = """使い方\n
`使い方`: このメッセージを表示\n
`未承認`: 未承認の購入承認リクエスト一覧を表示\n
`承認 1 2 3 | 承認 1-3`: ID 1, 2, 3の購入承認リクエストを承認\n
`却下 1 2 3 | 却下 1-3`: ID 1, 2, 3の購入承認リクエストを却下\n
`無視 1 2 3 | 無視 1-3`: ID 1, 2, 3の購入承認リクエストを無視"""


VALID_ID_RANGE = 10
MIN_NOTIFICATION_SECONDS = 60


def check_id_range(start_id, end_id):
    """ IDの範囲が有効であるか確認する
    1. start_id <= end_id であるかどうか
    2. end_id - start_id < VALID_ID_RANGEであるかどうか

    :return: 有効であるかどうか、メッセージ
    """
    if end_id < start_id:
        return 'ID1-ID2では、ID1はID2以下である必要があります。'
    elif end_id - start_id > VALID_ID_RANGE:
        return '一度に{}個より多くのIDは選択できません。'.format(VALID_ID_RANGE)

    return None


def get_request_id(text):
    """ 文字列から複数のIDを取得する

    :param str text: "承認 1 123 1456" のような文字列
    :rtype: list[str]
    :return: ID のリスト
    """

    texts = text.split(' ')

    ids = []
    msg = ''

    for text in texts[1:]:
        if text.count('-') >= 2:
            msg += 'WRONG_REQUEST {} : 0より小さいIDを使っている可能性があります。\n'.format(text)
        # Parser for 「REQUEST ID1-IDN」
        elif text.count('-') == 1:
            start_id, end_id = text.split('-', 1)

            try:
                start_id = int(start_id)
                end_id = int(end_id)
            except ValueError:
                msg += 'WRONG_REQUEST {0} : 0以上の半角数字以外が含まれています。\n'.format(text)
                continue

            msg_for_wrong_usage = check_id_range(start_id, end_id)
            if msg_for_wrong_usage:
                msg += 'WRONG_REQUEST ' + text + ' : ' + msg_for_wrong_usage + '\n'
            else:
                ids.extend(list(range(start_id, end_id + 1)))

        # Parser for 「REQUEST ID1 ID2 ... IDN」
        else:
            try:
                ids.append(int(text))
            except ValueError:
                msg += 'WRONG_REQUEST {}: IDは整数でなければなりません。\n'.format(text)

    # 重複している要素を除いた後、ソートする
    ids = sorted(list(set(ids)))
    return ids, msg


class PurchaseBot:
    """ 購入承認ボット """
    USERNAME = 'purchase_bot'
    USER_ICON = ':yen:'
    REACTION_ICON = 'yen'

    def __init__(self, debug=False):
        self._logger = logging.getLogger("purchase_bot")
        self._logger.setLevel(logging.DEBUG if debug else logging.INFO)
        self._logger.addHandler(logging.StreamHandler())
        token = os.environ["SLACK_TOKEN"]
        purchase_channel = os.environ["SLACK_CHANNEL_ID"]
        self._purchase_channel = purchase_channel
        self.client = SlackClient(token)
        self.repo = PurchaseRepo()
        self._logger.info("connected to redis")
        self._last_notified = datetime.datetime.now()

    def _send_direct_message(self, user_id, message):
        """ 特定ユーザにDMを送信 """
        im_id = self.client.api_call("im.open", user=user_id)["channel"]["id"]
        self.client.api_call("chat.postMessage", channel=im_id, text=message,
                             username=self.USERNAME, icon_emoji=self.USER_ICON)

    def _post_channel(self, message):
        """ チャンネルに投稿 """
        self.client.api_call("chat.postMessage", channel=self._purchase_channel, text=message,
                             username=self.USERNAME, icon_emoji=self.USER_ICON)

    def _post_channel_color(self, message1, color, message2):
        """ チャンネルに色付きで投稿 """
        self.client.api_call("chat.postMessage", channel=self._purchase_channel, text=message1,
                             attachments=[{"color": color, "text": message2}],
                             username=self.USERNAME, icon_emoji=self.USER_ICON)

    def _add_reaction(self, message):
        """ メッセージにリアクションを返す """
        self.client.api_call("reactions.add", name=self.REACTION_ICON,
                             channel=self._purchase_channel, timestamp=message["ts"])

    def _get_username(self, user_id):
        """ 特定IDのユーザのユーザ名を取得する

        :param str user_id: ユーザID
        :rtype: str
        :return: ユーザ名
        """
        result = self.client.api_call("users.info", user=user_id)
        return result["user"]["name"]

    def _create_new_request(self, text, user_id):
        request_id = self.repo.get_id()
        username = self._get_username(user_id)
        request = PurchaseRequest(request_id, user_id, username, text)
        self.repo.create_or_update(request)

    def _purchase_request(self, message):
        """ #purchase チャンネルの承認者以外のリクエストを処理する """
        if message.get('type') != 'message':
            return False
        # 承認者からの申請は無視
        if message.get('user') in self.repo.admin:
            return False
        # purchase_channel 以外は無視
        if message.get('channel') != self._purchase_channel:
            return False
        # スレッド内は無視
        if message.get('thread_ts'):
            return False

        sub_type = message.get('subtype')
        if not sub_type:
            self._create_new_request(message["text"], message["user"])
            self._add_reaction(message)
            return True
        elif sub_type == "message_changed":
            prev_text = message["previous_message"].get("text")
            user = message["previous_message"].get("user")
            username = self._get_username(user)
            new_text = message["message"].get("text")
            if not self.repo.update(username, prev_text, new_text):
                self._logger.error("Failed to update request: {}".format(message))
                return True
        elif sub_type == "message_deleted":
            prev_text = message["previous_message"].get("text")
            user = message["previous_message"].get("user")
            username = self._get_username(user)
            if not self.repo.delete(username, prev_text):
                self._logger.error("Failed to delete request: {}".format(message))
            return True
        return False

    def _register_admin(self, user_id, text):
        """ 承認者登録 or 解除 """
        if text.find("承認者登録") >= 0:
            if user_id in self.repo.admin:
                self._send_direct_message(user_id, "承認者登録済みです")
            else:
                self.repo.add_admin(user_id)
                self._send_direct_message(user_id, "承認者登録しました")
            return True
        elif text.find("承認者解除") >= 0:
            if user_id in self.repo.admin:
                self.repo.remove_admin(user_id)
                self._send_direct_message(user_id, "承認者登録解除しました")
            else:
                self._send_direct_message(user_id, "承認者登録されていません")
            return True
        return False

    def _handle_command(self, message):
        """ コマンドを処理する """
        if message.get('type') != 'message':
            return False
        # ダイレクトメッセージのみを扱う
        if not message.get('channel').startswith('D'):
            return False

        user_id = message.get('user')
        if not user_id:
            return False

        text = unicodedata.normalize("NFKC", message["text"])
        if not text:
            return False

        if text.find("承認者") >= 0:
            if self._register_admin(user_id, text):
                return True

        # 以下は管理者用コマンド
        if user_id not in self.repo.admin:
            self._send_direct_message(user_id, "承認者以外は利用できません")
            return False

        if text.find("使い方") >= 0:
            self._send_direct_message(user_id, USAGE)
            return True

        if text.find("未承認") >= 0:
            self._notify_unapproved(user_id, force=True)
            return True

        admin_name = self._get_username(user_id)
        if text.startswith("承認"):
            request_ids, msg = get_request_id(text)
            if request_ids:
                for request_id in request_ids:
                    request, new = self._is_new_request(user_id, request_id)
                    if new:
                        msg1 = ">>> <@{}|{}>: {}".format(
                            request.user_id, request.username, request.text)
                        msg2 = "上記購入承認リクエストは承認されました (リクエスト番号は{}番, 承認者は <@{}|{}> です)".format(
                            request_id, user_id, admin_name)
                        self._post_channel_color(msg1, "good", msg2)
                        self._send_direct_message(
                            user_id, "ID: {} を承認しました".format(request_id))
                        self.repo.approve(request_id, admin_name)

                self._send_direct_message(user_id, msg)
                return True
            else:
                self._send_direct_message(user_id, msg)
                return False

        elif text.startswith("却下"):
            request_ids, msg = get_request_id(text)
            if request_ids:
                for request_id in request_ids:
                    request, new = self._is_new_request(user_id, request_id)
                    if new:
                        msg1 = ">>> <@{}|{}>: {}".format(
                            request.user_id, request.username, request.text)
                        msg2 = "上記購入承認リクエストは却下されました (リクエスト番号は{}番です, 承認者は <@{}|{}> です)".format(
                            request_id, user_id, admin_name)
                        self._post_channel_color(msg1, "danger", msg2)
                        self._send_direct_message(
                            user_id, "ID: {} を却下しました".format(request_id))
                        self.repo.deny(request_id, admin_name)
                self._send_direct_message(user_id, msg)
                return True
            else:
                self._send_direct_message(user_id, msg)
                return False

        elif text.startswith("無視"):
            request_ids, msg = get_request_id(text)
            if request_ids:
                for request_id in request_ids:
                    request, new = self._is_new_request(user_id, request_id)
                    if new:
                        self._send_direct_message(
                            user_id, "ID: {} を無視しました".format(request_id))
                        # 無視も一旦 deny 扱い
                        self.repo.deny(request_id, admin_name)
                self._send_direct_message(user_id, msg)
                return True
            else:
                self._send_direct_message(user_id, msg)
                return False

        self._send_direct_message(user_id, "不明なコマンドです: {}".format(text))
        return False

    def _is_new_request(self, user_id, request_id):
        """

        :param str user_id: リクエストの問い合わせを行った承認者のID
        :param (int|str) request_id: リクエストのID
        :rtype: (PurchaseRequest|None), bool
        :return: 取得したリクエストとそのリクエストが未対応か否か
        """
        request, new = self.repo.get(request_id)
        if not request:
            self._send_direct_message(
                user_id, "ID: {} が見つかりません".format(request_id))
        elif not new:
            self._send_direct_message(
                user_id, "ID: {} は既に対応済みです".format(request_id))
        return request, new

    def _notify_unapproved(self, user=None, force=False):
        """ 未承認の購入承認リクエストについて報告する """
        now = datetime.datetime.now()
        if not force and now - self._last_notified < datetime.timedelta(seconds=MIN_NOTIFICATION_SECONDS):
            return
        requests = self.repo.get_new()
        if requests:
            message = "未承認の購入承認リクエストが {}件あります。\n".format(len(requests))
            for request in requests:
                message += "-----\n"
                message += request.to_message()
            if user is None:
                for admin in self.repo.admin:
                    self._send_direct_message(admin, message)
            else:
                self._send_direct_message(user, message)
        elif user:
            self._send_direct_message(user, "未承認の購入承認リクエストはありません")
        self._last_notified = now

    def _handle_message(self, message):
        """ メッセージが届いた際のメイン処理 """
        if self._purchase_request(message):
            self._notify_unapproved()
        else:
            self._handle_command(message)

    def _update(self):
        messages = self.client.rtm_read()
        for message in messages:
            self._logger.debug(message)
            self._handle_message(message)

    def main(self):
        if not self.client.rtm_connect():
            raise RuntimeError('failed to connect slack, invalid token?')
        self.client.api_call("users.setActive")
        self._logger.info("Begin main loop")
        while True:
            self._update()
            time.sleep(0.1)
