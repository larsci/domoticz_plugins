
# Netatmo API Reader Plugin

# Author: Ycahome, 2017

# Version:    1.0.0: Initial Version

"""
<plugin key="LC-Netatmo" name="Netatmo module reader" author="lcp" version="1.0.0" wikilink="" externallink="">
    <params>
        <param field="Mode1" label="Netatmo client id" width="800px" required="true" default=""/>
        <param field="Mode2" label="Netatmo client secret" width="800px" required="true" default=""/>
        <param field="Mode5" label="Netatmo refresh token" width="800px" required="true" default=""/>
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
import paho.mqtt.client as mqtt
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
    THERM_TEMP_B1 = 3
    THERM_TEMP_B2 = 4
    THERM_TEMP_BU = 5
    CO2_B1 = 6
    CO2_B2 = 7
    BARO_B1 = 8
    HUMIDITY_B1 = 9
    HUMIDITY_B2 = 10
    HUMIDITY_BU = 11
    BARO_TREND_B1 = 12
    THERM_SETP_MODE = 13
    THERM_ON = 14


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

NETATMO_DEVICES = [
#   ID,                    NAME,                TYPE,  SUBTYPE,  SWITCHTYPE, OPTIONS,                NAME,        MODBUSSCALE,            FORMAT,    PREPEND,        LOOKUP
     [Unit.THERM_TEMP,     "ThermTemp",         80,    5,        0x00,       {},                     "temperature",     "temperature_scale",    "{:.2f}",  None,           None ],
     [Unit.THERM_SETP,     "ThermSetpoint",     242,   1,        0x00,       {},                     "temperature",     "temperature_scale",    "{:.2f}",  None,           None ],
     [Unit.THERM_TEMP_B1,  "TempB1",            80,    5,        0x00,       {},                     "temperature",     "temperature_scale",    "{:.2f}",  None,           None ],
     [Unit.THERM_TEMP_B2,  "TempB2",            80,    5,        0x00,       {},                     "temperature",     "temperature_scale",    "{:.2f}",  None,           None ],
     [Unit.THERM_TEMP_BU,  "TempBU",            80,    5,        0x00,       {},                     "temperature",     "temperature_scale",    "{:.2f}",  None,           None ],
     [Unit.CO2_B1,         "CO2B1",             249,   1,        0x00,       {},                     "airquality",      "airquality_scale",    "{:.2f}",  None,           None ],
     [Unit.CO2_B2,         "CO2B2",             249,   1,        0x00,       {},                     "airquality",      "airquality_scale",    "{:.2f}",  None,           None ],
     [Unit.BARO_B1,        "BaroB1",            243,   26,       0x00,       {},                     "pressure",        "pressure_scale",    "{:.2f}",  None,           None ],
     [Unit.HUMIDITY_B1,    "HumB1",             81,    1,        0x00,       {},                     "humidity",        "humidity_scale",    "{:.2f}",  None,           None ],
     [Unit.HUMIDITY_B2,    "HumB2",             81,    1,        0x00,       {},                     "humidity",        "humidity_scale",    "{:.2f}",  None,           None ],
     [Unit.HUMIDITY_BU,    "HumBU",             81,    1,        0x00,       {},                     "humidity",        "humidity_scale",    "{:.2f}",  None,           None ],
     [Unit.BARO_TREND_B1,  "BaroTrendB1",       243,   19,       0x00,       {},                     "pressuretrend",   "pressure_scale",    "{:.2f}",  None,           None ],
     [Unit.THERM_SETP_MODE,"ThermSetpointMode", 243,   19,       0x00,       {},                     "ThermSetpointMode",   "pressure_scale",    "{:.2f}",  None,           None ],
     [Unit.THERM_ON,       "ThermStatusOn",     243,   19,       0x00,       {},                     "ThermStatusOn",   "pressure_scale",    "{:.2f}",  None,           None ],
   ]

#
# Domoticz shows graphs with intervals of 5 minutes.
# When collecting information from the inverter more frequently than that, then it makes no sense to only show the last value.
#
# The Maximum class can be used to calculate the highest value based on a sliding window of samples.
# The number of samples stored depends on the interval used to collect the value from the inverter itself.
#


_BASE_URL = "https://api.netatmo.com/"
_AUTH_REQ              = _BASE_URL + "oauth2/token"
_GETMEASURE_REQ        = _BASE_URL + "api/getmeasure"
_GETSTATIONDATA_REQ    = _BASE_URL + "api/getstationsdata"
_GETTHERMOSTATDATA_REQ = _BASE_URL + "api/getthermostatsdata"
_GETHOMEDATA_REQ       = _BASE_URL + "api/gethomedata"
_GETCAMERAPICTURE_REQ  = _BASE_URL + "api/getcamerapicture"
_GETEVENTSUNTIL_REQ    = _BASE_URL + "api/geteventsuntil"
_GETHOMESDATA_REQ      = _BASE_URL + "api/homesdata"
_GETHOMESTATUS_REQ     = _BASE_URL + "api/homestatus"

_MQTT_SERVER = "10.0.0.20"
_MQTT_PORT = 1883

class AuthFailure( Exception ):
    pass


class ClientAuth:
    """
    Request authentication and keep access token available through token method. Renew it automatically if necessary
    BREAKING CHANGE: 
        Netatmo seems no longer (july 2023) to allow grant_type "password", even for an app credentials that belong to the same account than the home.
        They have added the capability of creating access_token/refresh_token couple from the dev page (the location where app are created).
        As a consequence, the username/password credentials can no longer be used and you must replace them with a new parameter refresh_token that you will get from the web interface.
        To get this token, you are required to specify the scope you want to allow to this token. Select all that apply for your library use.
    Args:
        clientId (str): Application clientId delivered by Netatmo on dev.netatmo.com
        clientSecret (str): Application Secret key delivered by Netatmo on dev.netatmo.com
        clientRefreskToken (str): Application refresh token delivered by Netatmo on dev.netatmo.com
    """

    def __init__(self, clientId,
                       clientSecret,
                       clientRefreskToken):

        self.token_scope="read_station read_thermostat"
        
        self.token_postParams = {
                "grant_type" : "refresh_token",
                "client_id" : clientId,
                "client_secret" : clientSecret,
                "refresh_token" : clientRefreskToken,
                }

        self._clientId = clientId
        self._clientSecret = clientSecret

        self._accessToken = None
        self.refreshToken = ''
        self._scope = ''
        self.expiration = 0

    @property
    def resetAccessToken(self):
        self._accessToken is None
        
    @property
    def accessToken(self):
        
        if self._accessToken is None:
            Domoticz.Status('*** Get new token from Netatmo')
            try:
                resp = postRequest(_AUTH_REQ, self.token_postParams)
                if not resp: 
                    Domoticz.Error("Authentication request rejected")
                    self._accessToken = None
                else:
                    Domoticz.Debug('*** New token from Netatmo')
                    self._accessToken = resp["access_token"]
                    self.refreshToken = resp["refresh_token"]
                    self._scope = resp["scope"]
                    self.expiration = int(resp["expire_in"] + time.time())
            except BaseException as err:
                Domoticz.Error("Authentication token request error")
                Domoticz.Error(err)
                self._accessToken = None
            # finally:
        
        if not self._accessToken is None:
            if self.expiration < time.time(): # Token should be renewed
                Domoticz.Status('*** GET Refresh token from Netatmo')
                postParams = {
                        "grant_type" : "refresh_token",
                        "refresh_token" : self.refreshToken,
                        "client_id" : self._clientId,
                        "client_secret" : self._clientSecret
                        }
                try:
                    resp = postRequest(_AUTH_REQ, postParams)
                except BaseException as err:
                    Domoticz.Error("Refresh token request error")
                    Domoticz.Error(err)
                    self._accessToken = None

                if not resp or self._accessToken is None: 
                    Domoticz.Error("Authentication request refresh rejected")
                    self._accessToken = None
                    return None

                Domoticz.Status('*** Refresh token from Netatmo')
                self._accessToken = resp['access_token']
                self.refreshToken = resp['refresh_token']
                self.expiration = int(resp['expire_in'] + time.time())
            else:
                Domoticz.Status('*** Token from Netatmo reused')
        return self._accessToken


def postRequest(url, params=None, timeout=10):
    req = urllib.request.Request(url)
    if params:
        req.add_header("Content-Type","application/x-www-form-urlencoded;charset=utf-8")
        params = urllib.parse.urlencode(params).encode('utf-8')
    try:
        resp = urllib.request.urlopen(req, params, timeout=timeout) if params else urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as err:
        Domoticz.Error("postRequest error")
        Domoticz.Error(err)
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

class BasePlugin:

    def __init__(self):
        self.debug = False
        self.error = False
        self.nextpoll = datetime.now()
        self.pollinterval = 0
        self.userName = ""
        self.passWord = ""
        self.clientId = ""
        self.clientSecret = ""
        self.clientRefreshToken = ""
        self.authorization = None

        return

    def onStart(self):
        if Parameters["Mode4"] == "Debug":
            self.debug = True
            Domoticz.Debugging(1)
            DumpConfigToLog()
        else:
            Domoticz.Debugging(0)

        Domoticz.Debug("onStart called")
        
        self.mqtt_client = mqtt.Client("netatmo_to_mqtt")
        self.mqtt_client.on_publish = self.on_publish_mqtt
        self.mqtt_client.username_pw_set("hass", password="aH2801nuC")
        self.mqtt_client.connect(_MQTT_SERVER,_MQTT_PORT,6*60) 
        
        ret= self.mqtt_client.publish("netatmo_plugin","started") 
        Domoticz.Debug("start published")
        Domoticz.Debug(ret)

        self.userName = Parameters["Username"]
        self.passWord = Parameters["Password"]
        self.clientId = Parameters["Mode1"]
        self.clientSecret = Parameters["Mode2"]
        self.clientRefreshToken = Parameters["Mode5"]

        self.authorization = ClientAuth(self.clientId, self.clientSecret, self.clientRefreshToken)
        # check polling interval parameter
        try:
            temp = int(Parameters["Mode3"])
        except:
            Domoticz.Error("Invalid polling interval parameter")
            self.pollinterval = 15 * 60
        else:
            if temp < 1:
                temp = 5  # minimum polling interval
                Domoticz.Error("Specified polling interval too short: changed to 5 minutes")
            elif temp > 30:
                temp = 30  # maximum polling interval is 1 day
                Domoticz.Error("Specified polling interval too long: changed to 1440 minutes (1 day)")
            self.pollinterval = temp * 60

        Domoticz.Debug("Using polling interval of {} seconds".format(str(self.pollinterval)))

        for unit in NETATMO_DEVICES:
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
        ret= self.mqtt_client.publish("netatmo_plugin","stopped") 
        Domoticz.Debug("onStop called")
        Domoticz.Debugging(0)

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug(
            "onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))

    def on_publish_mqtt(client,userdata,result, aap):             #create function for callback
        Domoticz.Debug("mqtt data published")

    def onHeartbeat(self):
        Domoticz.Debug("onHeartbeat")
        # DumpConfigToLog()  
        now = datetime.now()
        ret= self.mqtt_client.publish("netatmo_plugin/heartbeat",now.strftime("%m/%d/%Y, %H:%M:%S")) 
        if now >= self.nextpoll:
            ret= self.mqtt_client.publish("netatmo_plugin/poll",datetime.now().strftime("%m/%d/%Y, %H:%M:%S")) 
            self.nextpoll = now + timedelta(seconds=self.pollinterval)
            Domoticz.Debug("onHeartbeat - Get sensors")
            authToken = self.authorization.accessToken

            if authToken is None: 
                Domoticz.Error("No authToken")
                return
            

            foundError = False
            foundThermData = False
            foundStationData = False
            foundHomeStatusData = False
            foundMeas = False
            # 
            # https://dev.netatmo.com/apidocumentation/control
            try:
                postParams = {
                        "access_token" : authToken,
                        "home_id": '5b8a9318ae476387748c3ae4'
                        }
                resp_homestatusdata = postRequest(_GETHOMESTATUS_REQ, postParams)
                if resp_homestatusdata is None: 
                    Domoticz.Error("*** Failed _GETHOMESTATUS_REQ (1)")
                    foundError =  True
                else:
                    if len(resp_homestatusdata) < 100:
                        foundHomeStatusData = True
                    else:
                        Domoticz.Error("*** Failed _GETHOMESTATUS_REQ data length error")
            except BaseException as err:
                Domoticz.Error('*** Failed _GETHOMESTATUS_REQ (2)')
                Domoticz.Error(err)
                foundError =  True

            # postParams = {
            #         "access_token" : authToken
            #         }
            # try:
            #     resp_therm = postRequest(_GETTHERMOSTATDATA_REQ, postParams)
            #     if resp_therm is None: 
            #         Domoticz.Error("*** Failed _GETTHERMOSTATDATA_REQ")
            #         foundError =  True
            #     else:
            #         foundThermData = True
            # except BaseException as err:
            #     Domoticz.Error('*** Failed _GETTHERMOSTATDATA_REQ')
            #     Domoticz.Error(err)
            #     foundError =  True

            # try:
            #     resp_station = postRequest(_GETSTATIONDATA_REQ, postParams)
            #     if resp_station is None: 
            #         Domoticz.Error("*** Failed _GETSTATIONDATA_REQ")
            #         foundError =  True
            #     else:
            #         foundStationData = True
            # except BaseException as err:
            #     Domoticz.Error('*** Failed _GETSTATIONDATA_REQ')
            #     Domoticz.Error(err)
            #     foundError =  True         

            # try:
            #     postParams = {
            #             "access_token" : authToken,
            #             "device_id": '04:00:00:ab:3a:ac',
            #             "scale": '30min'
            #             }
            #     resp_meas = postRequest(_GETMEASURE_REQ, postParams)
            #     if resp_meas is None: 
            #         Domoticz.Error("*** Failed _GETMEASURE_REQ")
            #         foundError =  True
            #     else:
            #         foundMeas = True
            # except BaseException as err:
            #     Domoticz.Error('*** Failed _GETMEASURE_REQ')
            #     Domoticz.Error(err)
            #     foundError =  True

            # Domoticz.Debug('_GETMEASURE_REQ')
            # Domoticz.Debug(resp_meas)

            if foundHomeStatusData:
                try:
                    statusBoiler = 'Unknown'
                    Domoticz.Debug("=== RESP _GETHOMESTATUS_REQ ===================================================================")
                    homeStatusRoom = resp_homestatusdata['body']['home']['rooms'][0]
                    homeStatus = resp_homestatusdata['body']['home']['modules']

                    # Hoofdmodule
                    NAMain_temperature = 0
                    NAMain_co2 = 0
                    NAMain_humidity = 0
                    NAMain_noise = 0
                    NAMain_pressure = 0
                    # Buitenmodule
                    NAModule1_temperature = 0
                    # NAModule1_co2 = 0
                    NAModule1_humidity = 0
                    # Binnenmodule
                    NAModule4_temperature = 0
                    NAModule4_co2 = 0
                    NAModule4_humidity = 0

                    Domoticz.Debug('homesData')
                    Domoticz.Debug(homeStatus)
                    Domoticz.Debug(statusBoiler)

                    thermSetpoint = homeStatusRoom['therm_setpoint_temperature']
                    thermTemp = homeStatusRoom['therm_measured_temperature']
                    thermSetpointMode = homeStatusRoom['therm_setpoint_mode']

                    Devices[Unit.THERM_SETP].Update(nValue=0, sValue=str(thermSetpoint), TimedOut=0)
                    Devices[Unit.THERM_TEMP].Update(nValue=0, sValue=str(thermTemp), TimedOut=0)
                    Devices[Unit.THERM_SETP_MODE].Update(nValue=0, sValue=str(thermSetpointMode), TimedOut=0)
                    
                    ret= self.mqtt_client.publish("netatmo_plugin/therm_setpoint",str(thermSetpoint)) 
                    ret= self.mqtt_client.publish("netatmo_plugin/therm_temp",str(thermTemp))
                    ret= self.mqtt_client.publish("netatmo_plugin/therm_setpoint_mode",str(thermSetpointMode))

                    for index, item in enumerate(homeStatus):
                        Domoticz.Debug(item)
                        if item['type'] == 'NATherm1': # Thermostaat
                            statusBoiler = resp_homestatusdata['body']['home']['modules'][index]['boiler_status']
                            break
                        if item['type'] == 'NAMain':    # Hoofdmodule
                            NAMain_temperature = resp_homestatusdata['body']['home']['modules'][index]['temperature']
                            NAMain_co2 = resp_homestatusdata['body']['home']['modules'][index]['co2']
                            NAMain_humidity = resp_homestatusdata['body']['home']['modules'][index]['humidity']
                            NAMain_noise = resp_homestatusdata['body']['home']['modules'][index]['noise']
                            NAMain_pressure = resp_homestatusdata['body']['home']['modules'][index]['pressure'] 
                        if item['type'] == 'NAModule1':    # Buitenmodule                      
                            NAModule1_temperature = resp_homestatusdata['body']['home']['modules'][index]['temperature']
                            # NAModule1_co2 = resp_homestatusdata['body']['home']['modules'][index]['co2']
                            NAModule1_humidity = resp_homestatusdata['body']['home']['modules'][index]['humidity']
                        if item['type'] == 'NAModule4':    # Binnenmodule                      
                            NAModule4_temperature = resp_homestatusdata['body']['home']['modules'][index]['temperature']
                            NAModule4_co2 = resp_homestatusdata['body']['home']['modules'][index]['co2']
                            NAModule4_humidity = resp_homestatusdata['body']['home']['modules'][index]['humidity']
                    
                    # soms komen er nul waardes voor (ondanks chack op foundHomeStatusData). NAMain... waardes zijn nooit 0
                    if NAMain_temperature > 0 and NAMain_humidity > 0:
                        Devices[Unit.THERM_ON].Update(nValue=0, sValue=str(statusBoiler), TimedOut=0)   
                        ret= self.mqtt_client.publish("netatmo_plugin/therm_on",statusBoiler)

                        Devices[Unit.THERM_TEMP_B1].Update(nValue=0, sValue=str(NAMain_temperature), TimedOut=0) 
                        Devices[Unit.HUMIDITY_B1].Update(nValue=NAMain_humidity, sValue=str(NAMain_humidity), TimedOut=0) 
                        Devices[Unit.CO2_B1].Update(nValue=NAMain_co2, sValue=str(NAMain_co2), TimedOut=0)
                        Devices[Unit.BARO_B1].Update(nValue=0, sValue=str(NAMain_pressure) + ";0" , TimedOut=0) 
                        ret= self.mqtt_client.publish("netatmo_plugin/temp_B1",str(NAMain_temperature))              
                        ret= self.mqtt_client.publish("netatmo_plugin/hum_B1",str(NAMain_humidity))              
                        ret= self.mqtt_client.publish("netatmo_plugin/co2_B1",str(NAMain_co2))               
                        ret= self.mqtt_client.publish("netatmo_plugin/pressure_B1",str(NAMain_pressure))   

                        Devices[Unit.THERM_TEMP_BU].Update(nValue=0, sValue=str(NAModule1_temperature), TimedOut=0)
                        Devices[Unit.HUMIDITY_BU].Update(nValue=NAModule1_humidity, sValue=str(NAModule1_humidity), TimedOut=0) 
                        ret= self.mqtt_client.publish("netatmo_plugin/temp_BU",str(NAModule1_temperature))              
                        ret= self.mqtt_client.publish("netatmo_plugin/hum_BU",str(NAModule1_humidity))   
    
                        Devices[Unit.THERM_TEMP_B2].Update(nValue=0, sValue=str(NAModule4_temperature), TimedOut=0)  
                        ret= self.mqtt_client.publish("netatmo_plugin/temp_B2",str(NAModule4_temperature))             
                        Devices[Unit.HUMIDITY_B2].Update(nValue=NAModule4_humidity, sValue=str(NAModule4_humidity), TimedOut=0)  
                        ret= self.mqtt_client.publish("netatmo_plugin/hum_B2",str(NAModule4_humidity))              
                        Devices[Unit.CO2_B2].Update(nValue=NAModule4_co2, sValue=str(NAModule4_co2), TimedOut=0)
                        ret= self.mqtt_client.publish("netatmo_plugin/co2_B2",str(NAModule4_co2)) 

                        # For now....
                        Devices[Unit.BARO_TREND_B1].Update(nValue=0, sValue=str(""), TimedOut=0) 
                        ret= self.mqtt_client.publish("netatmo_plugin/pressure_trend_BU","")  
                    else:
                        Domoticz.Error('*** _GETHOMESTATUS_REQ: zero values detected')

                except BaseException as err:
                    Domoticz.Error('*** Error in Netatmo homesData data structure!')
                    Domoticz.Error(err)
                    Domoticz.Error(resp_homestatusdata)
                    foundError =  True

            Domoticz.Debug("=== RESP _GETTHERMOSTATDATA_REQ ===================================================================")
            # if foundThermData:
            #     try:
            #         thermostatDataM = resp_therm['body']['devices'][0]['modules'][0]['measured']
            #         thermostatDataS = resp_therm['body']['devices'][0]['modules'][0]['setpoint']
            #         Devices[Unit.THERM_TEMP].Update(nValue=0, sValue=str(thermostatDataM['temperature']), TimedOut=0) 
            #         ret= self.mqtt_client.publish("netatmo_plugin/therm_temp",str(thermostatDataM['temperature']))  
            #         if thermostatDataS['setpoint_mode'] == 'manual':
            #             Devices[Unit.THERM_SETP].Update(nValue=0, sValue=str(thermostatDataS['setpoint_temp']), TimedOut=0)  
            #             ret= self.mqtt_client.publish("netatmo_plugin/therm_setpoint",str(thermostatDataS['setpoint_temp']))   
            #         else:
            #             Devices[Unit.THERM_SETP].Update(nValue=0, sValue=str(thermostatDataM['setpoint_temp']), TimedOut=0)  
            #             ret= self.mqtt_client.publish("netatmo_plugin/therm_setpoint",str(thermostatDataM['setpoint_temp'])) 
            #         Devices[Unit.THERM_SETP_MODE].Update(nValue=0, sValue=str(thermostatDataS['setpoint_mode']), TimedOut=0)  
            #         ret= self.mqtt_client.publish("netatmo_plugin/therm_setpoint_mode",str(thermostatDataS['setpoint_mode']))   


            #     except BaseException as err:
            #         Domoticz.Error('*** Error in Netatmo thermostat data structure!')
            #         Domoticz.Error(err)
            #         Domoticz.Error(resp_therm)
            #         foundError =  True
                    
            # if foundStationData:
            #     try:
            #         # basisstation binnen
            #         stationData = resp_station['body']['devices'][0]['dashboard_data']

            #         Devices[Unit.THERM_TEMP_B1].Update(nValue=0, sValue=str(stationData['Temperature']), TimedOut=0) 
            #         ret= self.mqtt_client.publish("netatmo_plugin/temp_B1",str(stationData['Temperature']))              
            #         Devices[Unit.HUMIDITY_B1].Update(nValue=stationData['Humidity'], sValue=str(stationData['Humidity']), TimedOut=0) 
            #         ret= self.mqtt_client.publish("netatmo_plugin/hum_B1",str(stationData['Humidity']))              
            #         Devices[Unit.CO2_B1].Update(nValue=stationData['CO2'], sValue=str(stationData['CO2']), TimedOut=0)
            #         ret= self.mqtt_client.publish("netatmo_plugin/co2_B1",str(stationData['CO2']))               
            #         Devices[Unit.BARO_B1].Update(nValue=0, sValue=str(stationData['Pressure']) + ";0" , TimedOut=0) 
            #         ret= self.mqtt_client.publish("netatmo_plugin/pressure_B1",str(stationData['Pressure']))               
            #     except BaseException as err:
            #         Domoticz.Error('*** Error in Netatmo stationData data structure!')
            #         Domoticz.Error(err)
            #         Domoticz.Error(resp_station)
            #         foundError =  True

            #     try:
            #         # module0 = buiten
            #         module0Data = resp_station['body']['devices'][0]['modules'][0]['dashboard_data']
            #         Domoticz.Debug('Netatmo Hum BU:')
            #         Domoticz.Debug(module0Data)
            #         Devices[Unit.THERM_TEMP_BU].Update(nValue=0, sValue=str(module0Data['Temperature']), TimedOut=0)
            #         ret= self.mqtt_client.publish("netatmo_plugin/temp_BU",str(module0Data['Temperature']))              
            #         Devices[Unit.HUMIDITY_BU].Update(nValue=module0Data['Humidity'], sValue=str(module0Data['Humidity']), TimedOut=0) 
            #         ret= self.mqtt_client.publish("netatmo_plugin/hum_BU",str(module0Data['Humidity']))   
            #         Devices[Unit.BARO_TREND_B1].Update(nValue=0, sValue=str(stationData['pressure_trend']), TimedOut=0) 
            #         ret= self.mqtt_client.publish("netatmo_plugin/pressure_trend_BU",str(stationData['pressure_trend']))                   
            #     except BaseException as err:
            #         Domoticz.Error('*** Error in Netatmo module0Data data structure!')
            #         Domoticz.Error(err)
            #         Domoticz.Error(resp_station)
            #         foundError =  True

            #     try:
            #         # module1 = binnen1
            #         module1Data = resp_station['body']['devices'][0]['modules'][1]['dashboard_data']
            #         Devices[Unit.THERM_TEMP_B2].Update(nValue=0, sValue=str(module1Data['Temperature']), TimedOut=0)  
            #         ret= self.mqtt_client.publish("netatmo_plugin/temp_B2",str(module1Data['Temperature']))             
            #         Devices[Unit.HUMIDITY_B2].Update(nValue=module1Data['Humidity'], sValue=str(module1Data['Humidity']), TimedOut=0)  
            #         ret= self.mqtt_client.publish("netatmo_plugin/hum_B2",str(module1Data['Humidity']))              
            #         Devices[Unit.CO2_B2].Update(nValue=module1Data['CO2'], sValue=str(module1Data['CO2']), TimedOut=0)
            #         ret= self.mqtt_client.publish("netatmo_plugin/co2_B2",str(module1Data['CO2']))                 
            #     except BaseException as err:
            #         Domoticz.Error('*** Error in Netatmo module1Data data structure!')
            #         Domoticz.Error(err)
            #         Domoticz.Error(resp_station)
            #         foundError =  True

            Domoticz.Debug("onHeartbeat - Set devices")
            Domoticz.Debug("----------------------------------------------------")
            if foundError:
                # make sure next time we get a clean connection with new token
                self.authorization.resetAccessToken()

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

