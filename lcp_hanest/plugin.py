
# HANest Reader Plugin

# Author: Ycahome, 2017

# Version:    1.0.0: Initial Version

"""
<plugin key="LCP-HA-Nest" name="HANest reader" author="lcp" version="1.0.0" wikilink="" externallink="">
    <params>
        <param field="Mode1" label="HA URL" width="800px" required="true" default=""/>
        <param field="Mode2" label="HA Token" width="800px" required="true" default=""/>
        <param field="Mode3" label="Update every x minutes" width="200px" required="true" default="15"/>
        <param field="Mode4" label="Debug" width="75px">
            <options>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal" default="true"/>
            </options>
        </param>
    </params>
</plugin>
"""

from inspect import Parameter
import Domoticz
import json
import urllib.request
import urllib.error
import time
from enum import IntEnum
from os import path
import sys
sys.path
sys.path.append('/usr/lib/python3/dist-packages')

from math import radians, cos, sin, asin, sqrt
from datetime import datetime, timedelta
#from unidecode import unidecode

#
# The plugin is using a few tables to setup Domoticz
# The Column class is used to easily identify the columns in those tables.
#
# @unique
class Unit(IntEnum):

    THERM_TEMP   = 1
    THERM_SETP   = 2
    THERM_SETP_MODE = 3
    THERM_ON = 4
    HUMIDITY_WK = 5

# @unique
class Column(IntEnum):

    ID              = 0
    NAME            = 1
    TYPE            = 2
    SUBTYPE         = 3
    SWITCHTYPE      = 4
    OPTIONS         = 5
    MODBUSNAME      = 6
    MODBUSSCALE     = 7
    FORMAT          = 8
    PREPEND         = 9
    LOOKUP          = 10

HA_NEST_DEVICES = [
#   ID,                    NAME,                TYPE,  SUBTYPE,  SWITCHTYPE, OPTIONS,                NAME,        MODBUSSCALE,            FORMAT,    PREPEND,        LOOKUP
     [Unit.THERM_TEMP,     "NestThermTemp",         80,    5,        0x00,       {},                 "temperature",         "temperature_scale",    "{:.2f}",  None,           None ],
     [Unit.THERM_SETP,     "NestThermSetpoint",     242,   1,        0x00,       {},                 "temperature",         "temperature_scale",    "{:.2f}",  None,           None ],
     [Unit.THERM_SETP_MODE,"NestThermSetpointMode", 243,   19,       0x00,       {},                 "ThermSetpointMode",   "pressure_scale",       "{:.2f}",  None,           None ],
     [Unit.THERM_ON,       "NestThermStatusOn",     243,   19,       0x00,       {},                 "ThermStatusOn",       "pressure_scale",       "{:.2f}",  None,           None ],
     [Unit.HUMIDITY_WK,    "NestThermHum",          81,    1,        0x00,       {},                 "humidity",            "humidity_scale",       "{:.2f}",  None,           None ],
   ]

#
# Domoticz shows graphs with intervals of 5 minutes.
# When collecting information from the inverter more frequently than that, then it makes no sense to only show the last value.
#
# The Maximum class can be used to calculate the highest value based on a sliding window of samples.
# The number of samples stored depends on the interval used to collect the value from the inverter itself.
#


_BASE_URL               = "http://10.0.0.20:8123/"
_HA_STATES              =  "api/states"
_HA_STATE_WK_CLIMATE    =  "api/states/climate.living_room"
_HA_STATE_WK_TEMP       =  "api/states/sensor.living_room_temperatuur"
_HA_STATE_WK_HUM       =  "api/states/sensor.living_room_luchtvochtigheid"

class AuthFailure( Exception ):
    pass


# class ClientAuth:
#     """
#     Request authentication and keep access token available through token method. Renew it automatically if necessary
#     BREAKING CHANGE: 
#         Netatmo seems no longer (july 2023) to allow grant_type "password", even for an app credentials that belong to the same account than the home.
#         They have added the capability of creating access_token/refresh_token couple from the dev page (the location where app are created).
#         As a consequence, the username/password credentials can no longer be used and you must replace them with a new parameter refresh_token that you will get from the web interface.
#         To get this token, you are required to specify the scope you want to allow to this token. Select all that apply for your library use.
#     Args:
#         clientId (str): Application clientId delivered by Netatmo on dev.netatmo.com
#         clientSecret (str): Application Secret key delivered by Netatmo on dev.netatmo.com
#         clientRefreskToken (str): Application refresh token delivered by Netatmo on dev.netatmo.com
#     """

#     def __init__(self, clientId,
#                        clientSecret,
#                        clientRefreskToken):

#         self.token_scope="read_station read_thermostat"
        
#         self.token_postParams = {
#                 "grant_type" : "refresh_token",
#                 "client_id" : clientId,
#                 "client_secret" : clientSecret,
#                 "refresh_token" : clientRefreskToken,
#                 }

#         self._clientId = clientId
#         self._clientSecret = clientSecret

#         self._accessToken = None
#         self.refreshToken = ''
#         self._scope = ''
#         self.expiration = 0

#     @property
#     def resetAccessToken(self):
#         self._accessToken is None
        
#     @property
#     def accessToken(self):
        
#         if self._accessToken is None:
#             Domoticz.Status('*** Get new token from Netatmo')
#             try:
#                 resp = postRequest(_AUTH_REQ, self.token_postParams)
#                 if not resp: 
#                     Domoticz.Error("Authentication request rejected")
#                     self._accessToken = None
#                 else:
#                     Domoticz.Debug('*** New token from Netatmo')
#                     self._accessToken = resp["access_token"]
#                     self.refreshToken = resp["refresh_token"]
#                     self._scope = resp["scope"]
#                     self.expiration = int(resp["expire_in"] + time.time())
#             except BaseException as err:
#                 Domoticz.Error("Authentication token request error")
#                 Domoticz.Error(err)
#                 self._accessToken = None
#             # finally:
        
#         if not self._accessToken is None:
#             if self.expiration < time.time(): # Token should be renewed
#                 Domoticz.Status('*** GET Refresh token from Netatmo')
#                 postParams = {
#                         "grant_type" : "refresh_token",
#                         "refresh_token" : self.refreshToken,
#                         "client_id" : self._clientId,
#                         "client_secret" : self._clientSecret
#                         }
#                 try:
#                     resp = postRequest(_AUTH_REQ, postParams)
#                 except BaseException as err:
#                     Domoticz.Error("Refresh token request error")
#                     Domoticz.Error(err)
#                     self._accessToken = None

#                 if not resp or self._accessToken is None: 
#                     Domoticz.Error("Authentication request refresh rejected")
#                     self._accessToken = None
#                     return None

#                 Domoticz.Status('*** Refresh token from Netatmo')
#                 self._accessToken = resp['access_token']
#                 self.refreshToken = resp['refresh_token']
#                 self.expiration = int(resp['expire_in'] + time.time())
#             else:
#                 Domoticz.Status('*** Token from Netatmo reused')
#         return self._accessToken


def postRequest(url, params=None, timeout=10):
    req = urllib.request.Request(url)
    if params:
        req.add_header("Content-Type","application/x-www-form-urlencoded;charset=utf-8")
        params = urllib.parse.urlencode(params).encode('utf-8')
    try:
        resp = urllib.request.urlopen(req, params, timeout=timeout) if params else urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as err:
        Domoticz.Error("postRequest error")
        Domoticz.Error("err")
        return None
    data = b""
    try:
        for buff in iter(lambda: resp.read(65535), b''): data += buff
        returnedContentType = resp.getheader("Content-Type")
        jsonStr = data.decode("utf-8") if "application/json" in returnedContentType else data
        return json.loads(jsonStr) if "application/json" in returnedContentType else data
    except BaseException as err:
        Domoticz.Error('*** postRequest; error reading datastream')
        Domoticz.Error(err)
        Domoticz.Error(jsonStr)
        return None

def getRequest(url, token, timeout=10):
    req = urllib.request.Request(url)
    req.add_header("Content-Type","application/x-www-form-urlencoded;charset=utf-8")
    req.add_header("Authorization", token)

    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as err:
        Domoticz.Error("getRequest error")
        Domoticz.Error("err")
        return None
    data = b""
    try:
        for buff in iter(lambda: resp.read(65535), b''): data += buff
        returnedContentType = resp.getheader("Content-Type")
        jsonStr = data.decode("utf-8") if "application/json" in returnedContentType else data
        return json.loads(jsonStr) if "application/json" in returnedContentType else data
    except BaseException as err:
        Domoticz.Error('*** getRequest; error reading datastream')
        Domoticz.Error(err)
        Domoticz.Error(jsonStr)
        return None

class BasePlugin:

    def __init__(self):
        self.debug = False
        self.error = False
        self.nextpoll = datetime.now()
        self.pollinterval = 0
        self.haUrl = ""
        self.haToken = ""


        return

    def onStart(self):
        if Parameters["Mode4"] == "Debug":
            self.debug = True
            Domoticz.Debugging(1)
            DumpConfigToLog()
        else:
            Domoticz.Debugging(0)

        Domoticz.Debug("onStart called")

        self.haUrl = Parameters["Mode1"]
        # "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIzMGY0MmQ4Zjg1OTE0ZTdjYjUyMDAxZjViNWQzMDM3YyIsImlhdCI6MTY5NDAyNjIxOSwiZXhwIjoyMDA5Mzg2MjE5fQ.hXoN0WLhyQpe5L7UdgbwQ_uuNviqLoa6E_PdTphyuoo"
        self.haToken = Parameters["Mode2"]

        # check polling interval parameter
        try:
            temp = int(Parameters["Mode3"])
        except:
            Domoticz.Error("Invalid polling interval parameter")
            self.pollinterval = 15 * 60
        else:
            if temp < 1:
                temp = 1  # minimum polling interval
                Domoticz.Error("Specified polling interval too short: changed to 1 minutes")
            elif temp > 30:
                temp = 30  # maximum polling interval is 1 day
                Domoticz.Error("Specified polling interval too long: changed to 1440 minutes (1 day)")
            self.pollinterval = temp * 60

        Domoticz.Debug("Using polling interval of {} seconds".format(str(self.pollinterval)))

        for unit in HA_NEST_DEVICES:
            if unit[Column.ID] not in Devices:
                Domoticz.Device(
                    Unit=unit[Column.ID],
                    Name=unit[Column.NAME],
                    Type=unit[Column.TYPE],
                    Subtype=unit[Column.SUBTYPE],
                    Switchtype=unit[Column.SWITCHTYPE],
                    Options=unit[Column.OPTIONS],
                    Used=1,
                ).Create()

    def onStop(self):
        Domoticz.Debug("onStop called")
        Domoticz.Debugging(0)

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug(
            "onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))

    def onHeartbeat(self):
        Domoticz.Debug("onHeartbeat")
        # DumpConfigToLog()  
        now = datetime.now()
        if now >= self.nextpoll:
            self.nextpoll = now + timedelta(seconds=self.pollinterval)
            Domoticz.Debug("onHeartbeat - Get sensors")          

            foundError = False
            foundWkClimateData = False
            foundWkTempData = False
            foundWkHumData = False
            try:
                resp_wkClimateData = getRequest(self.haUrl + _HA_STATE_WK_CLIMATE, self.haToken)
                if resp_wkClimateData is None: 
                    Domoticz.Error("*** Failed _HA_STATE_WK_CLIMATE")
                    foundError =  True
                else:
                    foundWkClimateData = True
            except BaseException as err:
                Domoticz.Error('*** Failed _HA_STATE_WK_CLIMATE')
                Domoticz.Error(err)
                foundError =  True

            try:
                resp_wkTempData = getRequest(self.haUrl + _HA_STATE_WK_TEMP, self.haToken)
                if resp_wkTempData is None: 
                    Domoticz.Error("*** Failed _HA_STATE_WK_TEMP")
                    foundError =  True
                else:
                    foundWkTempData = True
            except BaseException as err:
                Domoticz.Error('*** Failed _HA_STATE_WK_TEMP')
                Domoticz.Error(err)
                foundError =  True

            try:
                resp_wkHumData = getRequest(self.haUrl + _HA_STATE_WK_HUM, self.haToken)
                if resp_wkHumData is None: 
                    Domoticz.Error("*** Failed _HA_STATE_WK_HUM")
                    foundError =  True
                else:
                    foundWkHumData = True
            except BaseException as err:
                Domoticz.Error('*** Failed _HA_STATE_WK_HUM')
                Domoticz.Error(err)
                foundError =  True       

            if foundWkClimateData:
                Domoticz.Debug("=== RESP _HA_STATE_WK_CLIMATE ===================================================================")
                try:
                    # print(resp_url_wk_c['last_updated'])
                    # print(resp_url_wk_c['state'])
                    # print(resp_url_wk_c['attributes']['hvac_action'])
                    # print(resp_url_wk_c['attributes']['preset_mode'])
                    # print(resp_url_wk_c['attributes']['temperature'])
                    # print(resp_url_wk_c['attributes']['current_temperature'])
                    homesStatusBoiler = resp_wkClimateData['state'] + '/' + resp_wkClimateData['attributes']['preset_mode']
                    thermostatDataS = resp_wkClimateData['attributes']['temperature']
                    heatingStatus = resp_wkClimateData['attributes']['hvac_action']
                    Domoticz.Debug('resp_wkClimateData')
                    Domoticz.Debug(resp_wkClimateData)
                    Domoticz.Debug(homesStatusBoiler)
                    Domoticz.Debug(thermostatDataS)
                    heatingStatusBool = "False"
                    if heatingStatus == "heating": heatingStatusBool = "True"
                    Devices[Unit.THERM_ON].Update(nValue=0, sValue=str(heatingStatusBool), TimedOut=0)
                    Devices[Unit.THERM_SETP_MODE].Update(nValue=0, sValue=str(homesStatusBoiler), TimedOut=0)
                    Devices[Unit.THERM_SETP].Update(nValue=0, sValue=str(thermostatDataS), TimedOut=0)                   
                except BaseException as err:
                    Domoticz.Error('*** Error in HA Nest data structure!')
                    Domoticz.Error(err)
                    Domoticz.Error(resp_wkClimateData)
                    foundError =  True

            if foundWkTempData:
                Domoticz.Debug("=== RESP _HA_STATE_WK_TEMP ===================================================================")
                try:
                    thermostatDataM = resp_wkTempData['state']
                    Domoticz.Debug('resp_wkTempData')
                    Domoticz.Debug(resp_wkTempData)
                    Domoticz.Debug(thermostatDataM)
                    # thermostatDataMFl = float(resp_wkTempData['state'])
                    Devices[Unit.THERM_TEMP].Update(nValue=0, sValue=str(thermostatDataM), TimedOut=0)                     
                except BaseException as err:
                    Domoticz.Error('*** Error in HA Nest data structure!')
                    Domoticz.Error(err)
                    Domoticz.Error(resp_wkTempData)
                    foundError =  True

            if foundWkHumData:
                Domoticz.Debug("=== RESP _HA_STATE_WK_HUM ===================================================================")
                try:
                    thermostatDataH = resp_wkHumData['state']
                    Domoticz.Debug('resp_wkHumData')
                    Domoticz.Debug(resp_wkHumData)
                    Domoticz.Debug(thermostatDataH)
                    Domoticz.Debug(int(thermostatDataH))
                    thermostatDataHInt = int(thermostatDataH)
                    Devices[Unit.HUMIDITY_WK].Update(nValue=thermostatDataHInt, sValue=str(thermostatDataHInt), TimedOut=0)   
                    # Devices[Unit.HUMIDITY_BU].Update(nValue=module0Data['Humidity'], sValue=str(module0Data['Humidity']), TimedOut=0)                     
                except BaseException as err:
                    Domoticz.Error('*** Error in HA Nest data structure!')
                    Domoticz.Error(err)
                    Domoticz.Error(resp_wkHumData)
                    foundError =  True

            Domoticz.Debug("onHeartbeat - END")
            Domoticz.Debug("----------------------------------------------------")

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

#############################################################################
#                   Device specific functions                     #
#############################################################################


# Generic helper functions


def DumpConfigToLog():
    for x in Parameters:
      if Parameters[x] != "":
          Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    return

#
# Parse an int and return None if no int is given
#

def parseIntValue(s):

        try:
            return int(s)
        except:
            return None

#
# Parse a float and return None if no float is given
#

def parseFloatValue(s):

        try:
            return float(s)
        except:
            return None

