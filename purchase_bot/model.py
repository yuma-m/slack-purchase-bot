import json
from enum import Enum


class RequestStatus(Enum):
    new = "new"
    approved = "approved"
    denied = "denied"


class PurchaseRequest:
    """ 購入承認リクエスト
    
    :param str identity: 購入リクエストのID
    :param str user_id: ユーザID
    :param str username: ユーザの表示名
    :param str text: リクエスト内容
    :param RequestStatus status: リクエストの承認状況
    :param (None|str) approver: リクエストの承認者
    """

    def __init__(self, identity, user_id, username, text, status=RequestStatus.new, approver=None):
        self.id = int(identity)
        self.user_id = user_id
        self.username = username
        self.text = text
        self.status = status
        self._approver = approver

    def __repr__(self):
        return "<PurchaseRequest: id: {}, user: {}>".format(self.id, self.username)

    def to_str(self):
        dic = {"id": self.id, "user_id": self.user_id, "username": self.username, "text": self.text}
        return json.dumps(dic, ensure_ascii=False)

    @classmethod
    def from_str(cls, value_str, status=RequestStatus.new, approver=None):
        """ 文字列から PurchaseRequest を生成する

        :param str value_str: to_str メソッドで書き出した JSON 文字列
        :param RequestStatus status: リクエストの承認状況
        :rtype: PurchaseRequest
        """
        dic = json.loads(value_str)
        return cls(dic["id"], dic.get("user_id", ""), dic.get("username", ""), dic["text"], status, approver)

    def to_message(self):
        message = "ID: {}, <@{}|{}>: {}\n".format(self.id, self.user_id, self.username, self.text)
        return message

    @property
    def approver(self):
        if self._approver:
            return self._approver
        return ""
