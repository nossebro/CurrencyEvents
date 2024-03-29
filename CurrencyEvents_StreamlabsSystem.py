#---------------------------------------
#   Import Libraries
#---------------------------------------
import logging
from logging.handlers import TimedRotatingFileHandler
import clr
import re
import os
import codecs
import json
import random
clr.AddReference("websocket-sharp.dll")
from WebSocketSharp import WebSocket

#---------------------------------------
#   [Required] Script Information
#---------------------------------------
ScriptName = "CurrencyEvents"
Website = "https://github.com/nossebro/CurrencyEvents"
Creator = "nossebro"
Version = "0.0.8"
Description = "Add StreamLabs Currency to Users when Events are received on the local SLCB socket"

#---------------------------------------
#   Script Variables
#---------------------------------------
ScriptSettings = None
LocalAPI = None
Logger = None
LocalSocket = None
LocalSocketIsConnected = False
SettingsFile = os.path.join(os.path.dirname(__file__), "Settings.json")
UIConfigFile = os.path.join(os.path.dirname(__file__), "UI_Config.json")
APIKeyFile = os.path.join(os.path.dirname(__file__), "API_Key.js")

#---------------------------------------
#   Script Classes
#---------------------------------------
class StreamlabsLogHandler(logging.StreamHandler):
	def emit(self, record):
		try:
			message = self.format(record)
			Parent.Log(ScriptName, message)
			self.flush()
		except (KeyboardInterrupt, SystemExit):
			raise
		except:
			self.handleError(record)

class Settings(object):
	def __init__(self, settingsfile=None):
		defaults = self.DefaultSettings(UIConfigFile)
		try:
			with codecs.open(settingsfile, encoding="utf-8-sig", mode="r") as f:
				settings = json.load(f, encoding="utf-8")
			self.__dict__ = defaults.update(settings)
		except:
			self.__dict__ = defaults

	def DefaultSettings(self, settingsfile=None):
		defaults = dict()
		with codecs.open(settingsfile, encoding="utf-8-sig", mode="r") as f:
			ui = json.load(f, encoding="utf-8")
		for key in ui:
			try:
				defaults[key] = ui[key]['value']
			except:
				if key != "output_file":
					Parent.Log(ScriptName, "DefaultSettings(): Could not find key {0} in settings".format(key))
		return defaults

	def Reload(self, jsondata):
		self.__dict__ = self.DefaultSettings(UIConfigFile).update(json.loads(jsondata, encoding="utf-8"))

#---------------------------------------
#   Script Functions
#---------------------------------------
def GetLogger():
	log = logging.getLogger(ScriptName)
	log.setLevel(logging.DEBUG)

	sl = StreamlabsLogHandler()
	sl.setFormatter(logging.Formatter("%(funcName)s(): %(message)s"))
	sl.setLevel(logging.INFO)
	log.addHandler(sl)

	fl = TimedRotatingFileHandler(filename=os.path.join(os.path.dirname(__file__), "info"), when="w0", backupCount=8, encoding="utf-8")
	fl.suffix = "%Y%m%d"
	fl.setFormatter(logging.Formatter("%(asctime)s  %(funcName)s(): %(levelname)s: %(message)s"))
	fl.setLevel(logging.INFO)
	log.addHandler(fl)

	if ScriptSettings.DebugMode:
		dfl = TimedRotatingFileHandler(filename=os.path.join(os.path.dirname(__file__), "debug"), when="h", backupCount=24, encoding="utf-8")
		dfl.suffix = "%Y%m%d%H%M%S"
		dfl.setFormatter(logging.Formatter("%(asctime)s  %(funcName)s(): %(levelname)s: %(message)s"))
		dfl.setLevel(logging.DEBUG)
		log.addHandler(dfl)

	log.debug("Logger initialized")
	return log

def GetAPIKey(apifile=None):
	API = dict()
	try:
		with codecs.open(apifile, encoding="utf-8-sig", mode="r") as f:
			lines = f.readlines()
		matches = re.search(r"\"\s?([0-9a-f]+)\".*\"\s?(ws://[0-9.:]+/\w+)\"", "".join(lines))
		if matches:
			API["Key"] = matches.group(1)
			API["Socket"] = matches.group(2)
			Logger.debug("Got Key ({0}) and Socket ({1}) from API_Key.js".format(matches.group(1), matches.group(2)))
	except:
		Logger.critical("API_Key.js is missing in script folder")
	return API

#---------------------------------------
#   Chatbot Initialize Function
#---------------------------------------
def Init():
	global ScriptSettings
	ScriptSettings = Settings(SettingsFile)
	global Logger
	Logger = GetLogger()

	global LocalSocket
	global LocalAPI
	LocalAPI = GetAPIKey(APIKeyFile)
	if all (keys in LocalAPI for keys in ("Key", "Socket")):
		LocalSocket = WebSocket(LocalAPI["Socket"])
		LocalSocket.OnOpen += LocalSocketConnected
		LocalSocket.OnClose += LocalSocketDisconnected
		LocalSocket.OnMessage += LocalSocketEvent
		LocalSocket.OnError += LocalSocketError
		LocalSocket.Connect()
	
	Parent.AddCooldown(ScriptName, "LocalSocket", 10)

#---------------------------------------
#   Chatbot Script Unload Function
#---------------------------------------
def Unload():
	global LocalSocket
	if LocalSocket:
		LocalSocket.Close(1000, "Program exit")
		LocalSocket = None
		Logger.debug("LocalSocket Disconnected")
	global Logger
	if Logger:
		for handler in Logger.handlers[:]:
			Logger.removeHandler(handler)
		Logger = None

#---------------------------------------
#   Chatbot Save Settings Function
#---------------------------------------
def ReloadSettings(jsondata):
	ScriptSettings.Reload(jsondata)
	Logger.debug("Settings reloaded")

	if LocalSocket and not LocalSocket.IsAlive:
		if all (keys in LocalAPI for keys in ("Key", "Socket")):
			LocalSocket.Connect()

	Parent.BroadcastWsEvent('{0}_UPDATE_SETTINGS'.format(ScriptName.upper()), json.dumps(ScriptSettings.__dict__))
	Logger.debug(json.dumps(ScriptSettings.__dict__), True)

#---------------------------------------
#   Chatbot Execute Function
#---------------------------------------
def Execute(data):
	pass

#---------------------------------------
#   Chatbot Tick Function
#---------------------------------------
def Tick():
	global LocalSocketIsConnected
	if not Parent.IsOnCooldown(ScriptName, "LocalSocket") and LocalSocket and not LocalSocketIsConnected and all (keys in LocalAPI for keys in ("Key", "Socket")):
		Logger.warning("No EVENT_CONNECTED received from LocalSocket, reconnecting")
		try:
			LocalSocket.Close(1006, "No connection confirmation received")
		except:
			Logger.error("Could not close LocalSocket gracefully")
		LocalSocket.Connect()
		Parent.AddCooldown(ScriptName, "LocalSocket", 10)
	if not Parent.IsOnCooldown(ScriptName, "LocalSocket") and LocalSocket and not LocalSocket.IsAlive:
		Logger.warning("LocalSocket seems dead, reconnecting")
		try:
			LocalSocket.Close(1006, "No connection")
		except:
			Logger.error("Could not close LocalSocket gracefully")
		LocalSocket.Connect()
		Parent.AddCooldown(ScriptName, "LocalSocket", 10)

#---------------------------------------
#   LocalSocket Connect Function
#---------------------------------------
def LocalSocketConnected(ws, data):
	global LocalAPI
	Auth = {
		"author": Creator,
		"website": Website,
		"api_key": LocalAPI["Key"],
		"events": ScriptSettings.Events.split(",")
	}
	ws.Send(json.dumps(Auth))
	Logger.debug("Auth: {0}".format(json.dumps(Auth)))

#---------------------------------------
#   LocalSocket Disconnect Function
#---------------------------------------
def LocalSocketDisconnected(ws, data):
	global LocalSocketIsConnected
	LocalSocketIsConnected = False
	if data.Reason:
		Logger.debug("{0}: {1}".format(data.Code, data.Reason))
	elif data.Code == 1000 or data.Code == 1005:
		Logger.debug("{0}: Normal exit".format(data.Code))
	else:
		Logger.debug("{0}: Unknown reason".format(data.Code))
	if not data.WasClean:
		Logger.warning("Unclean socket disconnect")

#---------------------------------------
#   LocalSocket Error Function
#---------------------------------------
def LocalSocketError(ws, data):
	Logger.error(data.Message)
	if data.Exception:
		Logger.exception(data.Exception)

#---------------------------------------
#   LocalSocket Event Function
#---------------------------------------
def LocalSocketEvent(ws, data):
	if data.IsText:
		event = json.loads(data.Data)
		if "data" in event and isinstance(event["data"], str):
			event["data"] = json.loads(event["data"])
		Logger.debug(json.dumps(event, indent=4))
		if event["event"] == "EVENT_CONNECTED":
			global LocalSocketIsConnected
			LocalSocketIsConnected = True
			Logger.info(event["data"]["message"])
		# Twitch Cheer
		elif event["event"] == "TWITCH_BIT_V1":
			Points = int(round(float(event["data"]["bits"]) * (float(ScriptSettings.TwitchBits) / 100)))
			if event["data"].get("is_anonymous", None):
				ActiveUsers = random.shuffle(Parent.GetActiveUsers()[:])
				for x in ScriptSettings.Blacklist.split(","):
					if x.lower() in ActiveUsers:
						del ActiveUsers[x.lower()]
				User = ActiveUsers.pop(0)
				if Points > 0:
					Parent.SendStreamMessage(ScriptSettings.TwitchAnonBits.format(Name, event["data"]["bits"], Points))
					Parent.AddPoints(User, Parent.GetDisplayName(User), Points)
				Logger.debug("Anonymous cheered {1} bits, adding {2} points to {0}".format(Name, event["data"]["bits"], Points))
			else:
				if Points > 0:
					Parent.SendStreamMessage(ScriptSettings.TwitchBitsMessage.format(event["data"]["display_name"], event["data"]["bits"], Points))
					Parent.AddPoints(event["data"]["user_name"], event["data"]["display_name"], Points)
				Logger.debug("{0} cheered {1} bits, adding {2} points".format(event["data"]["display_name"], event["data"]["bits"], Points))
		elif event["event"] == "EVENT_CHEER":
			Points = int(round(float(event["data"]["bits"]) * (float(ScriptSettings.TwitchBits) / 100)))
			if event["data"]["name"]:
				if Points > 0:
					Parent.SendStreamMessage(ScriptSettings.TwitchBitsMessage.format(event["data"]["display_name"], event["data"]["bits"], Points))
					Parent.AddPoints(event["data"]["name"], event["data"]["display_name"], Points)
				Logger.debug("{0} cheered {1} bits, adding {2} points".format(event["data"]["display_name"], event["data"]["bits"], Points))
			else:
				ActiveUsers = random.shuffle(Parent.GetActiveUsers()[:])
				for x in ScriptSettings.Blacklist.split(","):
					if x.lower().strip() in ActiveUsers:
						del ActiveUsers[x.lower()]
				User = ActiveUsers.pop(0)
				if Points > 0:
					Parent.SendStreamMessage(ScriptSettings.TwitchAnonBits.format(Name, event["data"]["bits"], Points))
					Parent.AddPoints(User, Parent.GetDisplayName(User), Points)
				Logger.debug("Anonymous cheered {1} bits, adding {2} points to {0}".format(Name, event["data"]["bits"], Points))

		# Twitch Follow
		elif event["event"] == "EVENT_FOLLOW":
			Points = ScriptSettings.TwitchFollow
			if Points > 0:
				Parent.SendStreamMessage(ScriptSettings.TwitchFollowMessage.format(event["data"]["display_name"], Points))
				Parent.AddPoints(event["data"]["name"], event["data"]["display_name"], Points)
			Logger.debug("{0} followed, adding {1} points".format(event["data"]["display_name"], Points))
		# Twitch Host
		elif event["event"] == "EVENT_HOST":
			Points = event["data"]["viewers"] * ScriptSettings.TwitchHost
			if Points > 0:
				Parent.SendStreamMessage(ScriptSettings.TwitchHostMessage.format(event["data"]["name"], event["data"]["viewers"], Points))
				Parent.AddPoints(event["data"]["name"], event["data"]["display_name"], Points)
			Logger.debug("{0} hosted with {1} viewers, adding {2} points".format(event["data"]["name"], event["data"]["viewers"], Points))
		# Twitch Subscription
		elif event["event"] == "EVENT_SUB":
			if event["data"]["tier"] == "2":
				Points = ScriptSettings.TwitchTierTwo
			if event["data"]["tier"] == "3":
				Points = ScriptSettings.TwitchTierThree
			else:
				Points = ScriptSettings.TwitchTierOne
			if event["data"]["is_gift"]:
				# Split points between gifter/giftee according to settings, except when gifter is anonymous, bot or streamer.
				SubGifter = int(round(float(Points) * float(ScriptSettings.TwitchSubGifter / 100)))
				SubTarget = int(round(float(Points) * float(ScriptSettings.TwitchSubTarget / 100)))
				if event["data"]["name"].lower() not in { ScriptSettings.StreamerName.lower(), "anonymous" }:
					if SubGifter > 0:
						# {0} gifted {1} a subscription, adding {2} amount of currency for {0}
						Parent.SendStreamMessage(ScriptSettings.TwitchSubGiftMessage.format(event["data"]["display_name"], Parent.GetDisplayName(event["data"]["gift_target"]), SubGifter))
						Parent.AddPoints(event["data"]["name"], event["data"]["display_name"], SubGifter)
						Logger.debug("{0} gifted {1} a subscription, adding {2} points for {0}".format(event["data"]["display_name"], Parent.GetDisplayName(event["data"]["gift_target"]), SubGifter))
					if SubTarget > 0:
						# {0} gifted {1} a subscription, adding {2} amount of currency for {1}
						Parent.SendStreamMessage(ScriptSettings.TwitchSubTargetMessage.format(event["data"]["display_name"], Parent.GetDisplayName(event["data"]["gift_target"]), SubTarget))
						Parent.AddPoints(event["data"]["gift_target"], Parent.GetDisplayName(event["data"]["gift_target"]), SubTarget)
						Logger.debug("{0} was gifted a subscription, adding {1} points for {0}".format(Parent.GetDisplayName(event["data"]["gift_target"]), SubTarget))
				# Subscription is an anonymous gift, or made by streamer. All points to giftee.
				else:
					if SubGifter > 0:
						Parent.SendStreamMessage(ScriptSettings.TwitchSubTargetMessage.format(event["data"]["display_name"], Parent.GetDisplayName(event["data"]["gift_target"]), SubGifter))
						Parent.AddPoints(event["data"]["gift_target"], Parent.GetDisplayName(event["data"]["gift_target"]), SubGifter)
					Logger.debug("{0} gifted {1} a subscription, adding {2} points for {1}".format(event["data"]["display_name"], Parent.GetDisplayName(event["data"]["gift_target"]), SubGifter))
			else:
				if Points > 0:
					Parent.SendStreamMessage(ScriptSettings.TwitchSubMessage.format(event["data"]["display_name"], Points))
					Parent.AddPoints(event["data"]["name"], event["data"]["display_name"], Points)
				Logger.debug("{0} subscribed, adding {1} points".format(event["data"]["display_name"], Points))
		elif event["event"] == "TWITCH_SUB_V1":
			if event["data"]["sub_plan"] == 2000:
				Points = ScriptSettings.TwitchTierTwo
			if event["data"]["sub_plan"] == 3000:
				Points = ScriptSettings.TwitchTierThree
			else:
				Points = ScriptSettings.TwitchTierOne
			if event["data"].get("multi_month_duration", None):
				Points *= int(event["data"]["multi_month_duration"])
			if event["data"].get("is_gift", None):
				# Split points between gifter/giftee according to settings, except when gifter is anonymous, bot or streamer.
				SubGifter = int(round(float(Points) * float(ScriptSettings.TwitchSubGifter / 100)))
				SubTarget = int(round(float(Points) * float(ScriptSettings.TwitchSubTarget / 100)))
				if event["data"]["user_name"] not in { ScriptSettings.StreamerName.lower(), "anonymous" }:
					if SubGifter > 0:
						# {0} gifted {1} a subscription, adding {2} amount of currency for {0}
						Parent.SendStreamMessage(ScriptSettings.TwitchSubGiftMessage.format(event["data"]["display_name"], event["data"]["recipient_display_name"], SubGifter))
						Parent.AddPoints(event["data"]["user_name"], event["data"]["display_name"], SubGifter)
						Logger.debug("{0} gifted {1} a subscription, adding {2} points for {0}".format(event["data"]["display_name"], event["data"]["recipient_display_name"], SubGifter))
					if SubTarget > 0:
						# {0} gifted {1} a subscription, adding {2} amount of currency for {1}
						Parent.SendStreamMessage(ScriptSettings.TwitchSubTargetMessage.format(event["data"]["display_name"], event["data"]["recipient_display_name"], SubTarget))
						Parent.AddPoints(event["data"]["recipient_user_name"], event["data"]["recipient_display_name"], SubTarget)
						Logger.debug("{0} was gifted a subscription, adding {1} points for {0}".format(event["data"]["recipient_display_name"], SubTarget))
				# Subscription is an anonymous gift, or made by streamer. All points to giftee.
				else:
					if SubGifter > 0:
						Parent.SendStreamMessage(ScriptSettings.TwitchSubTargetMessage.format(event["data"]["display_name"], event["data"]["recipient_display_name"], SubGifter))
						Parent.AddPoints(event["data"]["recipient_user_name"], event["data"]["recipient_display_name"], SubGifter)
					Logger.debug("{0} gifted {1} a subscription, adding {2} points for {1}".format(event["data"]["display_name"], event["data"]["recipient_display_name"], SubGifter))
			else:
				if Points > 0:
					Parent.SendStreamMessage(ScriptSettings.TwitchSubMessage.format(event["data"]["display_name"], Points))
					Parent.AddPoints(event["data"]["user_name"], event["data"]["display_name"], Points)
				Logger.debug("{0} subscribed, adding {1} points".format(event["data"]["display_name"], Points))
		# Strealabs Donation
		elif event["event"] == "EVENT_DONATION":
			Points = int(round(float(event["data"]["amount"]) * float(ScriptSettings.StreamlabsDonation)))
			if Points > 0:
				Parent.SendStreamMessage(ScriptSettings.StreamlabsDonationMessage.format(event["data"]["display_name"], float(event["data"]["amount"]), event["data"]["currency"], Points))
				Parent.AddPoints(event["data"]["name"], event["data"]["display_name"], Points)
			Logger.debug("{0} donated {1} {2}, adding {3} points".format(event["data"]["display_name"], float(event["data"]["amount"]), event["data"]["currency"], Points))
		# Twitch Channel Points
		elif event["event"] == "TWITCH_REWARD_V1":
			Points = int(round(float(event["data"]["cost"]) * (float(ScriptSettings.TwitchChannelPoints) / 100)))
			if Points > 0:
				# {0} redeemed {1} channel points, adding {2} amount of currency
				Parent.SendStreamMessage(ScriptSettings.TwitchChannelPointsMessage.format(event["data"]["display_name"], event["data"]["cost"], Points))
				Parent.AddPoints(event["data"]["user_name"], event["data"]["display_name"], Points)
			Logger.debug("{0} redeemed {1} channel points, adding {2} amount of currency".format(event["data"]["display_name"], event["data"]["cost"], Points))
		else:
			Logger.warning("Unhandled event: {0}: {1}".format(event["event"], event["data"]))
