# -*- coding:utf-8 -*-
"""
Created on 2018-12-12

 * 微信支付帮助库
 * ====================================================
 * 接口分三种类型：
 * 【请求型接口】--Wxpay_client_
 *      统一支付接口类--UnifiedOrder
 *      订单查询接口--OrderQuery
 *      退款申请接口--Refund
 *      退款查询接口--RefundQuery
 *      对账单接口--DownloadBill
 *      短链接转换接口--ShortUrl
 * 【响应型接口】--Wxpay_server_
 *      通用通知接口--Notify
 *      Native支付——请求商家获取商品信息接口--NativeCall
 * 【其他】
 *      静态链接二维码--NativeLink
 *      JSAPI支付--JsApi
 * =====================================================
 * 【CommonUtil】常用工具：
 *      trimString()，设置参数时需要用到的字符处理函数
 *      createNoncestr()，产生随机字符串，不长于32位
 *      formatBizQueryParaMap(),格式化参数，签名过程需要用到
 *      getSign(),生成签名
 *      arrayToXml(),array转xml
 *      xmlToArray(),xml转 array
 *      postXmlCurl(),以post方式提交xml到对应的接口url
 *      postXmlSSLCurl(),使用证书，以post方式提交xml到对应的接口url

"""
from __future__ import unicode_literals
import logging
import hashlib
import json
import threading
import time
import random
import urllib2
import xml.etree.ElementTree as ET
from json import load
from urllib2 import urlopen
from urllib import quote

from django.conf import settings

try:
    import pycurl
    from cStringIO import StringIO
except ImportError:
    pycurl = None

import sys
reload(sys)
sys.setdefaultencoding('utf8')
log = logging.getLogger(__name__)


class WxH5PayConf_pub(object):
    """配置账号信息"""

    # =======【基本信息设置】=====================================
    # 微信公众号身份的唯一标识。审核通过后，在微信发送的邮件中查看
    APPID = settings.WECHAT_H5_PAY_INFO['basic_info']['APPID']
    # JSAPI接口中获取openid，审核后在公众平台开启开发模式后可查看
    APPSECRET = settings.WECHAT_H5_PAY_INFO['basic_info']['APPSECRET']
    # 受理商ID，身份标识
    MCHID = settings.WECHAT_H5_PAY_INFO['basic_info']['MCHID']
    # 商户支付密钥Key。审核通过后，在微信发送的邮件中查看
    KEY = settings.WECHAT_H5_PAY_INFO['basic_info']['KEY']
    ACCESS_TOKEN = settings.WECHAT_H5_PAY_INFO['basic_info']['ACCESS_TOKEN']

    SERVICE_TEL = settings.WECHAT_H5_PAY_INFO['other_info']['SERVICE_TEL']
    # =======【异步通知url设置】===================================
    # 异步通知url，商户根据实际开发过程设定
    NOTIFY_URL = settings.WECHAT_H5_PAY_INFO['other_info']['NOTIFY_URL']

    # =======【JSAPI路径设置】===================================
    # 获取access_token过程中的跳转uri，通过跳转将code传入jsapi支付页面
    JS_API_CALL_URL = settings.WECHAT_H5_PAY_INFO['other_info']['JS_API_CALL_URL']

    # =======【证书路径设置】=====================================
    # 证书路径,注意应该填写绝对路径
    SSLCERT_PATH = settings.WECHAT_H5_PAY_INFO['other_info']['SSLCERT_PATH']
    SSLKEY_PATH = settings.WECHAT_H5_PAY_INFO['other_info']['SSLKEY_PATH']
    # 上面为php版本专用

    # =======【curl超时设置】===================================
    CURL_TIMEOUT = 30

    # =======【HTTP客户端设置】===================================
    HTTP_CLIENT = "CURL"  # ("URLLIB", "CURL")
    SPBILL_CREATE_IP = settings.WECHAT_H5_PAY_INFO['other_info']['SPBILL_CREATE_IP']


class Singleton(object):
    """单例模式"""

    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "_instance"):
            with cls._instance_lock:
                if not hasattr(cls, "_instance"):
                    impl = cls.configure() if hasattr(cls, "configure") else cls
                    instance = super(Singleton, cls).__new__(impl, *args, **kwargs)
                    instance.__init__(*args, **kwargs)
                    cls._instance = instance
        return cls._instance


class UrllibClient(object):
    """使用urlib2发送请求"""

    def get(self, url, second=30):
        return self.postXml(None, url, second)

    def postXml(self, xml, url, second=30):
        """不使用证书"""
        data = urllib2.urlopen(url, xml.encode('utf-8'), timeout=second).read()
        return data

    def postXmlSSL(self, xml, url, second=30):
        """使用证书"""
        raise TypeError("please use CurlClient")


class CurlClient(object):
    """使用Curl发送请求"""
    def __init__(self):
        self.curl = pycurl.Curl()
        self.curl.setopt(pycurl.SSL_VERIFYHOST, False)
        self.curl.setopt(pycurl.SSL_VERIFYPEER, False)
        # 设置不输出header
        self.curl.setopt(pycurl.HEADER, False)

    def get(self, url, second=30):
        return self.postXmlSSL(None, url, second=second, cert=False, post=False)

    def postXml(self, xml, url, second=30):
        """不使用证书"""
        return self.postXmlSSL(xml, url, second=second, cert=False, post=True)

    def postXmlSSL(self, xml, url, second=30, cert=True, post=True):
        """使用证书"""
        self.curl.setopt(pycurl.URL, url)
        self.curl.setopt(pycurl.TIMEOUT, 30)
        # 设置证书
        # 使用证书：cert 与 key 分别属于两个.pem文件
        # 默认格式为PEM，可以注释
        if cert:
            self.curl.setopt(pycurl.SSLKEYTYPE, "PEM")
            self.curl.setopt(pycurl.SSLKEY, WxH5PayConf_pub.SSLKEY_PATH)
            self.curl.setopt(pycurl.SSLCERTTYPE, "PEM")
            self.curl.setopt(pycurl.SSLCERT, WxH5PayConf_pub.SSLCERT_PATH)
        # post提交方式
        if post:
            self.curl.setopt(pycurl.POST, True)
            self.curl.setopt(pycurl.POSTFIELDS, xml.encode('utf-8'))
        buff = StringIO()
        self.curl.setopt(pycurl.WRITEFUNCTION, buff.write)

        self.curl.perform()
        return buff.getvalue()


class HttpClient(Singleton):
    @classmethod
    def configure(cls):
        if pycurl is not None and WxH5PayConf_pub.HTTP_CLIENT != "URLLIB":
            return CurlClient
        else:
            return UrllibClient


class CommonH5_util_pub(object):
    """所有接口的基类"""

    def trimString(self, value):
        if value is not None and len(value) == 0:
            value = None
        return value

    def createNoncestr(self, length=32):
        """产生随机字符串，不长于32位"""
        chars = "abcdefghijklmnopqrstuvwxyz0123456789"
        strs = []
        for x in range(length):
            strs.append(chars[random.randrange(0, len(chars))])
        return "".join(strs)

    def formatBizQueryParaMap(self, paraMap, urlencode):
        """格式化参数，签名过程需要使用"""
        slist = sorted(paraMap)
        buff = []
        for k in slist:
            v = quote(paraMap[k]) if urlencode else paraMap[k]
            buff.append("{0}={1}".format(k, v))

        return "&".join(buff)

    def getSign(self, obj):
        """生成签名"""
        # 签名步骤一：按字典序排序参数,formatBizQueryParaMap已做
        String = self.formatBizQueryParaMap(obj, False)
        # 签名步骤二：在string后加入KEY
        String = "{0}&key={1}".format(String, WxH5PayConf_pub.KEY)
        # 签名步骤三：MD5加密
        String = hashlib.md5(String).hexdigest()
        # 签名步骤四：所有字符转为大写
        result_ = String.upper()
        return result_

    def arrayToXml(self, arr):
        """array转xml"""
        xml = ["<xml>"]
        for k, v in arr.iteritems():
            if v.isdigit():
                xml.append("<{0}>{1}</{0}>".format(k, v))
            else:
                xml.append("<{0}><![CDATA[{1}]]></{0}>".format(k, v))
        xml.append("</xml>")
        return "".join(xml)

    def xmlToArray(self, xml):
        """将xml转为array"""
        array_data = {}
        root = ET.fromstring(xml)
        for child in root:
            value = child.text
            array_data[child.tag] = value
        return array_data

    def postXmlCurl(self, xml, url, second=30):
        """以post方式提交xml到对应的接口url"""
        return HttpClient().postXml(xml, url, second=second)

    def postXmlSSLCurl(self, xml, url, second=30):
        """使用证书，以post方式提交xml到对应的接口url"""
        return HttpClient().postXmlSSL(xml, url, second=second)


class WxpayH5_client_pub(CommonH5_util_pub):
    """请求型接口的基类"""
    response = None   # 微信返回的响应
    url = None        # 接口链接
    curl_timeout = None  # curl超时时间

    def __init__(self):
        self.parameters = {}   # 请求参数，类型为关联数组
        self.result = {}       # 返回参数，类型为关联数组

    def setParameter(self, parameter, parameterValue):
        """设置请求参数"""
        self.parameters[self.trimString(parameter)] = self.trimString(parameterValue)

    def createXml(self):
        """设置标配的请求参数，生成签名，生成接口参数xml"""
        self.parameters["appid"] = WxH5PayConf_pub.APPID    # 公众账号ID
        self.parameters["mch_id"] = WxH5PayConf_pub.MCHID    # 商户号
        self.parameters["nonce_str"] = self.createNoncestr()    # 随机字符串
        self.parameters["sign"] = self.getSign(self.parameters)    # 签名
        return self.arrayToXml(self.parameters)

    def postXml(self):
        """post请求xml"""
        xml = self.createXml()
        self.response = self.postXmlCurl(xml, self.url, self.curl_timeout)
        return self.response

    def postXmlSSL(self):
        """使用证书post请求xml"""
        xml = self.createXml()
        self.response = self.postXmlSSLCurl(xml, self.url, self.curl_timeout)
        return self.response

    def getResult(self):
        """获取结果，默认不使用证书"""
        self.postXml()
        self.result = self.xmlToArray(self.response)
        return self.result


class UnifiedOrderH5_pub(WxpayH5_client_pub):
    """统一支付接口类"""

    def __init__(self, timeout=WxH5PayConf_pub.CURL_TIMEOUT):
        # 设置接口链接
        self.url = "https://api.mch.weixin.qq.com/pay/unifiedorder"
        # 设置curl超时时间
        self.curl_timeout = timeout
        super(UnifiedOrderH5_pub, self).__init__()

    def createXml(self):
        """生成接口参数xml"""
        # 检测必填参数
        if any(self.parameters[key] is None for key in ("out_trade_no", "body", "total_fee", "notify_url", "trade_type")):
            raise ValueError("missing parameter")
        if self.parameters["trade_type"] == "JSAPI" and self.parameters["openid"] is None:
            raise ValueError("JSAPI need openid parameters")

        self.parameters["appid"] = WxH5PayConf_pub.APPID   # 公众账号ID
        self.parameters["mch_id"] = WxH5PayConf_pub.MCHID    # 商户号
        self.parameters["nonce_str"] = self.createNoncestr()    # 随机字符串
        self.parameters["sign"] = self.getSign(self.parameters)    # 签名
        return self.arrayToXml(self.parameters)

    def getPrepayId(self):
        """获取prepay_id"""
        self.postXml()
        self.result = self.xmlToArray(self.response)
        prepay_id = self.result["prepay_id"]
        return prepay_id

    def getCodeUrl(self):
        """获取prepay_id"""
        self.postXml()
        self.result = self.xmlToArray(self.response)
        code_url = self.result["code_url"]
        return code_url

    def getMwebUrl(self):
        """获取mweb_url"""
        mweb_url = self.result["mweb_url"]
        return mweb_url

    def getUndResult(self):
        """获取sign"""
        self.result = self.xmlToArray(self.response)
        result = self.result
        return result

    def get_client_ip(self, request):
        try:
            ip = request.META['HTTP_X_REAL_IP']
        except Exception as ex:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[-1].strip()
            else:
                ip = request.META.get('REMOTE_ADDR')
        return ip

class OrderQueryH5_pub(WxpayH5_client_pub):
    """订单查询接口"""

    def __init__(self, timeout=WxH5PayConf_pub.CURL_TIMEOUT):
        # 设置接口链接
        self.url = "https://api.mch.weixin.qq.com/pay/orderquery"
        # 设置curl超时时间
        self.curl_timeout = timeout
        super(OrderQueryH5_pub, self).__init__()

    def createXml(self):
        """生成接口参数xml"""

        # 检测必填参数
        # if any(self.parameters[key] is None for key in ("out_trade_no", "transaction_id")):
            # raise ValueError("missing parameter")

        self.parameters["appid"] = WxH5PayConf_pub.APPID   # 公众账号ID
        self.parameters["mch_id"] = WxH5PayConf_pub.MCHID   # 商户号
        self.parameters["nonce_str"] = self.createNoncestr()   # 随机字符串
        self.parameters["sign"] = self.getSign(self.parameters)   # 签名
        return self.arrayToXml(self.parameters)


class ShortUrlH5_pub(WxpayH5_client_pub):
    """短链接转换接口"""

    def __init__(self, timeout=WxH5PayConf_pub.CURL_TIMEOUT):
        # 设置接口链接
        self.url = "https://api.mch.weixin.qq.com/tools/shorturl"
        # 设置curl超时时间
        self.curl_timeout = timeout
        super(ShortUrlH5_pub, self).__init__()

    def createXml(self):
        """生成接口参数xml"""
        if any(self.parameters[key] is None for key in ("long_url", )):
            raise ValueError("missing parameter")

        self.parameters["appid"] = WxH5PayConf_pub.APPID    # 公众账号ID
        self.parameters["mch_id"] = WxH5PayConf_pub.MCHID    # 商户号
        self.parameters["nonce_str"] = self.createNoncestr()    # 随机字符串
        self.parameters["sign"] = self.getSign(self.parameters)    # 签名
        return self.arrayToXml(self.parameters)

    def getShortUrl(self):
        """获取prepay_id"""
        self.postXml()
        prepay_id = self.result["short_url"]
        return prepay_id


class WxpayH5_server_pub(CommonH5_util_pub):
    """响应型接口基类"""
    SUCCESS, FAIL = "SUCCESS", "FAIL"

    def __init__(self):
        self.data = {}   # 接收到的数据，类型为关联数组
        self.returnParameters = {}   # 返回参数，类型为关联数组

    def saveData(self, xml):
        """将微信的请求xml转换成关联数组，以方便数据处理"""
        self.data = self.xmlToArray(xml)

    def checkSign(self):
        """校验签名"""
        tmpData = dict(self.data)   # make a copy to save sign
        del tmpData['sign']
        sign = self.getSign(tmpData)   # 本地签名
        if self.data['sign'] == sign:
            return True
        return False

    def getData(self):
        """获取微信的请求数据"""
        return self.data

    def setReturnParameter(self, parameter, parameterValue):
        """设置返回微信的xml数据"""
        self.returnParameters[self.trimString(parameter)] = self.trimString(parameterValue)

    def createXml(self):
        """生成接口参数xml"""
        return self.arrayToXml(self.returnParameters)

    def returnXml(self):
        """将xml数据返回微信"""
        returnXml = self.createXml()
        return returnXml

    def getProductId(self):
        """获取product_id"""
        product_id = self.data["product_id"]
        return product_id


class NotifyH5_pub(WxpayH5_server_pub):
    """通用通知接口"""
    def createXml(self):
        """生成接口参数xml"""
        self.returnParameters["appid"] = WxH5PayConf_pub.APPID   # 公众账号ID
        self.returnParameters["mch_id"] = WxH5PayConf_pub.MCHID   # 商户号
        self.returnParameters["nonce_str"] = self.createNoncestr()   # 随机字符串
        self.returnParameters["sign"] = self.getSign(self.returnParameters)   # 签名

        return self.arrayToXml(self.returnParameters)


class NativeCallH5_pub(WxpayH5_server_pub):
    """请求商家获取商品信息接口"""

    def createXml(self):
        """生成接口参数xml"""
        if self.returnParameters["return_code"] == self.SUCCESS:
            self.returnParameters["appid"] = WxH5PayConf_pub.APPID   # 公众账号ID
            self.returnParameters["mch_id"] = WxH5PayConf_pub.MCHID   # 商户号
            self.returnParameters["nonce_str"] = self.createNoncestr()   # 随机字符串
            self.returnParameters["sign"] = self.getSign(self.returnParameters)   # 签名

        return self.arrayToXml(self.returnParameters)

    def getProductId(self):
        """获取product_id"""
        product_id = self.data["product_id"]
        return product_id
