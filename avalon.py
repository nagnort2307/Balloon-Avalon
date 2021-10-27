import asyncio
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from random import randrange, shuffle
from typing import List, Mapping

from discord import DMChannel

from model import Team, Phase, Role, Quest, Player
from msgqueue import MsgQueue
from skins import Skin, Skins
from strings import StringSet, StringSets

SERVANT = Role(Team.GOOD, "servant")
MINION = Role(Team.EVIL, "minion",)
MERLIN = Role(Team.GOOD, "merlin")
PERCIVAL = Role(Team.GOOD, "percival")
ASSASSIN = Role(Team.EVIL, "assassin")
MORGANA = Role(Team.EVIL, "morgana")
MORDRED = Role(Team.EVIL, "mordred")
OBERON = Role(Team.EVIL, "oberon")
CLERIC = Role(Team.GOOD, "cleric")
LUNATIC = Role(Team.EVIL, "lunatic")
REVEALER = Role(Team.EVIL, "revealer")
TRICKSTER = Role(Team.EVIL, "trickster")
TROUBLEMAKER = Role(Team.GOOD, "troublemaker")
UNTRUSTWORTHY_SERVANT = Role(Team.GOOD, "untrustworthy")
#BRUTE = Role(Team.EVIL, "brute")

NAME_TO_ROLE = {
    SERVANT.key: SERVANT,
    MINION.key: MINION,
    MERLIN.key: MERLIN,
    PERCIVAL.key: PERCIVAL,
    ASSASSIN.key: ASSASSIN,
    MORGANA.key: MORGANA,
    MORDRED.key: MORDRED,
    OBERON.key: OBERON,
    CLERIC.key: CLERIC,
    LUNATIC.key: LUNATIC,
    REVEALER.key: REVEALER,
    TRICKSTER.key: TRICKSTER,
    TROUBLEMAKER.key: TROUBLEMAKER,
    UNTRUSTWORTHY_SERVANT.key: UNTRUSTWORTHY_SERVANT,
    #BRUTE.key: BRUTE,
}


@dataclass
class GameState:
    phase: Phase = Phase.INIT    # current game phase
    quest_selection = True      # whether leader may choose any incomplete quest
    enable_lady = False           # whether lady of the lake is enabled
    shuffle_table = False
    quests: List[Quest] = field(default_factory=list)
    players: List[Player] = field(default_factory=list)
    players_by_duid: Mapping[int, Player] = field(default_factory=dict)
    leader: int = 0              # index of leader player (0-based)
    current_quest: int = 1       # number of current quest (1-based)
    # remaining attempts to form team (incl. current one)
    team_attempts: int = 5
    current_party: List[Player] = field(default_factory=list)
    # past and current lady of the lake
    lady_players: List[Player] = field(default_factory=list)
    skin: Skin = Skins["AVALON"]
    prefix: str = "!"
    t: StringSet = StringSets["avalon-vi-base"].withDefaults(prefix=prefix)

    @property
    def succeeded_quests(self):
        return sum(quest.winning_team is Team.GOOD for quest in self.quests)

    @property
    def failed_quests(self):
        return sum(quest.winning_team is Team.EVIL for quest in self.quests)

    @property
    def completed_quests(self):
        return sum(quest.winning_team is not None for quest in self.quests)

    @property
    def current_lady(self):
        return self.lady_players[-1]

    def compileCommand(self, commandRegex):
        return re.compile(r'^' + re.escape(self.prefix) + commandRegex)

    def isCommand(self, message: str, command: str, exact=False) -> bool:
        return message.startswith(self.prefix) and (
            message[len(self.prefix):] == command or (
                exact is False and
                message[len(self.prefix):].startswith(command + ' ')
            )
        )


RE_PARTY_NAMES = r"party\s+.+"
RE_PARTY_QUEST_NAMES = r"party\s+(\d+)\s+.+"


def channel_check(channel):
    def _check(m):
        return m.channel == channel
    return _check


def add_channel_check(check, channel):
    def _check(m):
        return channel_check(channel)(m) and check(m)
    return _check


def setup_game(num_players, custom_roles):
    if num_players < 1 or num_players > 10:
        return None, None

    if num_players == 1:  # Test scenario
        quests = [Quest(1) for n in range(5)]
    elif num_players == 2:  # Test scenario
        quests = [Quest(2) for n in range(5)]
    elif num_players == 3:  # Test scenario
        quests = [Quest(2) for n in range(5)]
    elif num_players == 4:  # Test scenario
        quests = [Quest(2) for n in range(5)]
    else:
        adventurers = ([2, 3, 2, 3, 3] if num_players == 5
                       else [2, 3, 4, 3, 4] if num_players == 6
                       else [2, 3, 3, 4, 4] if num_players == 7
                       else [3, 4, 4, 5, 5])
        quests = [Quest(n) for n in adventurers]
    if num_players >= 7:
        quests[3].required_fails = 2

    if len(custom_roles) > 0:
        if num_players == 4:  # Test scenario
            good_count = 2
            evil_count = 2
        elif num_players == 5:
            good_count = 3
            evil_count = 2
        elif num_players == 6:
            good_count = 4
            evil_count = 2
        elif num_players == 7:
            good_count = 4
            evil_count = 3
        elif num_players == 8:
            good_count = 5
            evil_count = 3
        elif num_players == 9:
            good_count = 6
            evil_count = 3
        elif num_players == 10:
            good_count = 6
            evil_count = 4
        else:  # Test scenario
            good_count = num_players - 1
            evil_count = 1

        good_roles = [
            role for role in custom_roles if role.is_good
        ][:good_count]
        while len(good_roles) < good_count:
            good_roles.append(SERVANT)
        evil_roles = [
            role for role in custom_roles if role.is_evil
        ][:evil_count]
        while len(evil_roles) < evil_count:
            evil_roles.append(MINION)
        roles = good_roles + evil_roles

    else:
        if num_players == 1:  # Test scenario
            roles = [ASSASSIN]
        elif num_players == 2:  # Test scenario
            roles = [ASSASSIN, MERLIN]
        elif num_players == 3:  # Test scenario
            roles = [ASSASSIN] + [SERVANT, MERLIN]
        elif num_players == 4:  # Test scenario
            roles = [MINION, ASSASSIN] + [SERVANT, MERLIN]
        elif num_players == 5:
            roles = [SERVANT, MERLIN, PERCIVAL, ASSASSIN, MORGANA]
        elif num_players == 6:
            roles = 2 * [SERVANT] + [MERLIN, PERCIVAL, ASSASSIN, MORGANA]
        elif num_players == 7:
            roles = 2 * [SERVANT] + \
                [MERLIN, PERCIVAL, ASSASSIN, MORGANA, OBERON]
        elif num_players == 8:
            roles = 3 * [SERVANT] + \
                [MINION, MERLIN, PERCIVAL, ASSASSIN, MORGANA]
        elif num_players == 9:
            roles = 4 * [SERVANT] + \
                [MERLIN, PERCIVAL, ASSASSIN, MORDRED, MORGANA]
        elif num_players == 10:
            roles = 4 * [SERVANT] + 2 * [MINION] + \
                [MERLIN, PERCIVAL, ASSASSIN, MORGANA]
        else:
            roles = None
    return quests, roles


def detect_configuration(command_text: str, prefix: str):
    command = command_text.lower() + " "
    skin, strings = Skins["AVALON"], StringSets["avalon-vi-base"]
    if any(f' {x} ' in command for x in ["sw", "starwars", "star wars"]):
        strings = StringSets["avalon-en-starwars"]
        skin = Skins["STARWARS"]
    elif any(f' {x} ' in command for x in ["gs", "guerre stellari"]):
        strings = StringSets["avalon-it-starwars"]
        skin = Skins["STARWARS"]
    elif any(f' {x} ' in command for x in ["it", "ita", "italian", "italiano"]):
        strings = StringSets["avalon-it-base"]
    return skin, strings.withDefaults(prefix=prefix)


async def avalon(client, message, prefix):  # main loop
    gamestate = GameState(prefix=prefix)
    gamestate.skin, gamestate.t = detect_configuration(
        message.content, gamestate.prefix)
    await gamestate.skin.send_image(gamestate.skin.logo, message.channel)
    if gamestate.phase == Phase.INIT:
        await login_phase(client, message, gamestate)
    if gamestate.phase == Phase.NIGHT:
        await night_phase(client, message, gamestate)
    while gamestate.phase in (Phase.QUEST, Phase.TEAMVOTE, Phase.PRIVATEVOTE, Phase.LADY):
        if gamestate.phase == Phase.QUEST:
            await quest_phase(client, message, gamestate)
        if gamestate.phase == Phase.TEAMVOTE:
            await teamvote_phase(client, message, gamestate)
        if gamestate.phase == Phase.PRIVATEVOTE:
            await privatevote_phase(client, message, gamestate)
        if gamestate.phase == Phase.LADY:
            await lady_phase(client, message, gamestate)
    if gamestate.phase == Phase.GAMEOVER:
        await gameover_phase(client, message, gamestate)


async def login_phase(client, message, gamestate):
    # Login Phase
    gamestate.phase = Phase.LOGIN
    await message.channel.send(gamestate.t.loginStr())
    custom_roles = []
    with MsgQueue(client=client, check=channel_check(message.channel)) as msgqueue:
        while gamestate.phase == Phase.LOGIN:
            reply = await msgqueue.nextmsg()
            # RULE CHANGE COMMANDS
            if gamestate.isCommand(reply.content, 'roles', True):
                await confirm(reply)
                if len(custom_roles) > 0:
                    await message.channel.send(gamestate.t.selectedRoles(', '.join([x.key for x in custom_roles])))
                else:
                    await message.channel.send(gamestate.t.rolesInfo(', '.join(NAME_TO_ROLE.keys())))
            elif gamestate.isCommand(reply.content, 'roles'):
                custom_role_names = reply.content.split(' ')[1:]
                custom_role_names = [
                    name.lower() for name in custom_role_names if name != ''
                ]
                if len(custom_role_names) == 1 and custom_role_names[0] == 'reset':
                    await confirm(reply)
                    custom_roles = []
                    continue

                invalid_role_names = [
                    name for name in custom_role_names if not name in NAME_TO_ROLE
                ]
                if len(invalid_role_names) > 0:
                    await error(reply)
                    await message.channel.send(gamestate.t.roleNotValid(invalid_role_names[0]))
                    continue

                await confirm(reply)
                if not "merlin" in custom_role_names:
                    custom_role_names.append("merlin")
                    await message.channel.send(gamestate.t.merlinRequired)
                if not "assassin" in custom_role_names:
                    await message.channel.send(gamestate.t.noAssassin)
                custom_roles = [
                    NAME_TO_ROLE[name] for name in custom_role_names
                ]
                await message.channel.send(gamestate.t.rolesUpdated)

            if gamestate.isCommand(reply.content, 'rule'):
                parameters = reply.content.split(' ')[1:]
                if len(parameters) <= 0:
                    await confirm(reply)
                    await message.channel.send(gamestate.t.ruleCommandSyntax())
                    continue
                if len(parameters) > 2:
                    await error(reply)
                    await message.channel.send(gamestate.t.ruleCommandSyntax())
                    continue
                selected_rule = parameters[0]
                selected_action = parameters[1] if len(parameters) >= 2 else ""
                def do_check(): return False

                def do_set(on):
                    return on
                if selected_rule == "lady":
                    def do_check(): return gamestate.enable_lady

                    def do_set(on):
                        gamestate.enable_lady = on
                        return on
                elif selected_rule == "quest":
                    def do_check(): return gamestate.quest_selection

                    def do_set(on):
                        gamestate.quest_selection = on
                        return on
                elif selected_rule == "shuffle":
                    def do_check(): return gamestate.shuffle_table

                    def do_set(on):
                        gamestate.shuffle_table = on
                        return on
                else:
                    await error(reply)
                    await message.channel.send(gamestate.t.ruleCommandSyntax())
                    continue

                def do_toggle(): return do_set(False) if do_check() else do_set(True)
                if selected_action == "":
                    await confirm(reply)
                    await message.channel.send(gamestate.t.ruleCommandResult(selected_rule, do_check()))
                elif selected_action.lower() in ["on", "true"]:
                    await confirm(reply)
                    result = do_set(True)
                    await message.channel.send(gamestate.t.ruleCommandResult(selected_rule, result))
                elif selected_action.lower() in ["off", "false"]:
                    await confirm(reply)
                    result = do_set(False)
                    await message.channel.send(gamestate.t.ruleCommandResult(selected_rule, result))
                elif selected_action.lower() == "toggle":
                    await confirm(reply)
                    result = do_toggle()
                    await message.channel.send(gamestate.t.ruleCommandResult(selected_rule, result))
                else:
                    await error(reply)
                    await message.channel.send(gamestate.t.ruleCommandSyntax())
                    continue

            # JOIN COMMANDS
            if gamestate.isCommand(reply.content, "join") and len(gamestate.players) <= 10:
                if not any(p.user.id == reply.author.id for p in gamestate.players):
                    await confirm(reply)
                    await message.channel.send(gamestate.t.joinStr(reply.author.mention))
                    player = Player(reply.author.display_name, reply.author)
                    gamestate.players.append(player)
                    gamestate.players_by_duid[reply.author.id] = player
                    if len(gamestate.players) == 5:
                        await message.channel.send(gamestate.t.fiveStr())
                else:
                    await deny(reply)
                    await message.channel.send(gamestate.t.alreadyJoinedStr(reply.author.mention))
            if gamestate.isCommand(reply.content, "join") and len(gamestate.players) > 10:
                await deny(reply)
                await message.channel.send(gamestate.t.gameFullStr())
            # UNJOIN COMMANDS
            if gamestate.isCommand(reply.content, "unjoin"):
                if any(p.user.id == reply.author.id for p in gamestate.players):
                    await confirm(reply)
                    await message.channel.send(gamestate.t.unjoinStr(reply.author.mention))
                    player = Player(reply.author.display_name, reply.author)
                    gamestate.players.remove(player)
                else:
                    await deny(reply)
                    await message.channel.send(gamestate.t.failedUnjoinStr(reply.author.mention))
            # START COMMANDS
            if gamestate.isCommand(reply.content, "start") and len(gamestate.players) < 5:
                await deny(reply)
                await message.channel.send(gamestate.t.notEnoughPlayers)
            if (gamestate.isCommand(reply.content, "start") and len(gamestate.players) >= 5) or gamestate.isCommand(reply.content, "teststart"):
                await confirm(reply)
                # if gamestate.isCommand(reply.content, "teststart") and len(gamestate.players) == 1:
                #     command_args = reply.content.split(' ')
                #     if len(command_args) == 2 and command_args[1].isdigit():
                #         number = int(command_args[1])
                #         if 1 <= number <= 10:
                #             name = gamestate.players[0].name
                #             user = gamestate.players[0].user
                #             gamestate.players.extend([Player(name, user) for _ in range(number - 1)])  # Simulate 10 players with one
                gamestate.quests, roles_list = setup_game(
                    len(gamestate.players), custom_roles)
                if roles_list is None:
                    await message.channel.send(gamestate.t.ruleLoadingError)
                    continue
                players_str = ", ".join(p.name for p in gamestate.players)
                evil_count = sum(r.is_evil for r in roles_list)
                good_count = len(gamestate.players) - evil_count
                random.seed(datetime.now())
                shuffle(roles_list)
                if gamestate.shuffle_table:
                    shuffle(gamestate.players)
                for player, role in zip(gamestate.players, roles_list):
                    player.role = role
                gamestate.skin.assign_characters(gamestate.players)
                chars_list = [gamestate.t[p.char.stringID]
                              for p in gamestate.players]
                shuffle(chars_list)
                roles_str = "\n".join(
                    ":black_small_square: {}".format(r) for r in chars_list
                )
                await message.channel.send(gamestate.t.startStr(players_str, len(gamestate.players), good_count, evil_count, roles_str))
                gamestate.leader = 0  # leader will be in first seat
                leader_rotation = randrange(
                    len(gamestate.players)
                )  # leadercounter
                gamestate.players = gamestate.players[leader_rotation:] + \
                    gamestate.players[:leader_rotation]
                gamestate.lady_players.append(gamestate.players[-1])
                gamestate.phase = Phase.NIGHT

            # STOP COMMANDS
            if gamestate.isCommand(reply.content, "stop"):
                await confirm(reply)
                await message.channel.send(gamestate.t.stopStr())
                gamestate.phase = Phase.INIT


async def night_phase(client, message, gamestate):
    await message.channel.send(gamestate.t.nightStr)
    # evil players seen by each other
    evillist = [
        p for p in gamestate.players if p.role.is_evil and p.role is not OBERON
    ]
    # evil players seen by Merlin (exclude Mordred, include untrustworthy)
    merlinlist = [
        p for p in gamestate.players if (p.role.is_evil and p.role is not MORDRED or p.role is UNTRUSTWORTHY_SERVANT)
    ]
    # players seen by Percival
    percivallist = [
        p for p in gamestate.players if p.role in [MERLIN, MORGANA]
    ]

    assassin = None
    for p in gamestate.players:
        if p.role is ASSASSIN:
            assassin = p
            break

    shuffle(evillist)
    shuffle(merlinlist)
    shuffle(percivallist)

    def toString(players):
        return "\n".join(":black_small_square: {}".format(p.name) for p in players)

    for player in gamestate.players:
        # print(str(player.name)+" is "+ gamestate.t[player.char.stringID])	#Cheat code to reveal all roles for debugging purposes
        if player.role is SERVANT:
            secret = gamestate.t.loyalDM(
                player.name, gamestate.t[player.char.stringID])
        elif player.role is MINION:
            secret = gamestate.t.minionDM(
                player.name, gamestate.t[player.char.stringID], toString(evillist))
        elif player.role is MERLIN:
            secret = gamestate.t.merlinDM(
                player.name, gamestate.t[player.char.stringID], toString(merlinlist))
        elif player.role is ASSASSIN:
            secret = gamestate.t.assassinDM(
                player.name, gamestate.t[player.char.stringID], toString(evillist))
        elif player.role is MORDRED:
            secret = gamestate.t.mordredDM(
                player.name, gamestate.t[player.char.stringID], toString(evillist))
        elif player.role is MORGANA:
            secret = gamestate.t.morganaDM(
                player.name, gamestate.t[player.char.stringID], toString(evillist))
        elif player.role is PERCIVAL:
            secret = gamestate.t.percivalDM(
                player.name, gamestate.t[player.char.stringID], toString(percivallist))
        elif player.role is OBERON:
            secret = gamestate.t.oberonDM(
                player.name, gamestate.t[player.char.stringID])
        elif player.role is CLERIC:
            leader = gamestate.players[gamestate.leader]
            if player == leader:
                leaderLoyaltyMessage = gamestate.t.clericOnHimself
            elif leader.role is TROUBLEMAKER:
                leaderLoyaltyMessage = gamestate.t.minionMordred(leader.name)
            elif leader.role.is_good or leader.role is TRICKSTER:
                leaderLoyaltyMessage = gamestate.t.loyalArthur(leader.name)
            else:
                leaderLoyaltyMessage = gamestate.t.minionMordred(leader.name)
            secret = gamestate.t.clericDM(
             player.name, gamestate.t[player.char.stringID], leaderLoyaltyMessage)
        elif player.role is LUNATIC:
            secret = gamestate.t.lunaticDM(
                player.name, gamestate.t[player.char.stringID], toString(evillist))
        elif player.role is REVEALER:
            secret = gamestate.t.revealerDM(
                player.name, gamestate.t[player.char.stringID], toString(evillist))
        elif player.role is TRICKSTER:
            secret = gamestate.t.tricksterDM(
                player.name, gamestate.t[player.char.stringID], toString(evillist))
        elif player.role is TROUBLEMAKER:
            secret = gamestate.t.troublemakerDM(
                player.name, gamestate.t[player.char.stringID])
        elif player.role is UNTRUSTWORTHY_SERVANT:
            secret = gamestate.t.untrustworthyDM(player.name, gamestate.t[player.char.stringID]) + (
                gamestate.t.assassinAbsent if assassin is None else gamestate.t.assassinIs(assassin.name))
        else:
            secret = f"Error: Role not implemented ({player.role.key})"

        # if player.role is BRUTE:
        #     secret = gamestate.t.bruteDM(
        #         player.name, gamestate.t[player.char.stringID], toString(evillist))


        await player.user.send(secret, file=gamestate.skin.get_image_file(player.char.image_path))

    await message.channel.send(gamestate.t.night2Str)
    gamestate.phase = Phase.QUEST


def mentionToID(a: str):
    a = a.replace("<", "")
    a = a.replace(">", "")
    a = a.replace("@", "")
    a = a.replace("!", "")
    return a


async def quest_phase(client, message, gamestate):
    if gamestate.quest_selection:
        quest = None
        await gamestate.skin.send_table(gamestate, message.channel)
        await gamestate.skin.send_board(gamestate, message.channel)
        await message.channel.send(gamestate.t.teamReminderQuestSel(gamestate.players[gamestate.leader].user.mention))
    else:
        quest = gamestate.quests[gamestate.current_quest-1]
        await gamestate.skin.send_table(gamestate, message.channel)
        await gamestate.skin.send_board(gamestate, message.channel)
        await message.channel.send(gamestate.t.teamReminder(gamestate.players[gamestate.leader].user.mention, quest.adventurers))
    while gamestate.phase == Phase.QUEST:
        votetrigger = await client.wait_for("message", check=channel_check(message.channel))
        party_ptn = gamestate.compileCommand(
            RE_PARTY_QUEST_NAMES
        ) if gamestate.quest_selection else gamestate.compileCommand(
            RE_PARTY_NAMES
        )
        party_match = party_ptn.fullmatch(votetrigger.content)
        if party_match and votetrigger.author == gamestate.players[gamestate.leader].user:
            if gamestate.quest_selection:
                quest_num = int(party_match.group(1))
                if not 1 <= quest_num <= len(gamestate.quests):
                    await error(votetrigger)
                    await message.channel.send(gamestate.t.malformedQuestSel(len(gamestate.quests)))
                    continue
                quest = gamestate.quests[quest_num-1]
                if quest.winning_team is not None:
                    await deny(votetrigger)
                    await message.channel.send(gamestate.t.questAlreadyComplete(quest_num))
                    continue
                gamestate.current_quest = quest_num
            gamestate.current_party.clear()
            party_ids = set()
            valid = True
            for user in votetrigger.mentions:
                if user.id in party_ids:
                    await message.channel.send(gamestate.t.duplicateStr(quest.adventurers))
                    valid = False
                    break
                party_ids.add(user.id)
                if user.id not in gamestate.players_by_duid.keys():
                    await message.channel.send(gamestate.t.playernotingame(user.display_name))
                    valid = False
                    break
            if valid:
                if len(party_ids) == quest.adventurers:
                    await confirm(votetrigger)
                    gamestate.current_party = [
                        gamestate.players_by_duid[i] for i in party_ids]
                    gamestate.phase = Phase.TEAMVOTE
                else:
                    await error(votetrigger)
                    await message.channel.send(gamestate.t.malformedStr(quest.adventurers))
                # gamestate.phase = Phase.TEAMVOTE #cheatcode
        elif gamestate.isCommand(votetrigger.content, "stop"):
            await confirm(votetrigger)
            await message.channel.send(gamestate.t.stopStr())
            gamestate.phase = Phase.INIT
        elif votetrigger.author == gamestate.players[gamestate.leader].user and gamestate.isCommand(votetrigger.content, "party"):
            await error(votetrigger)
            await message.channel.send(gamestate.t.malformedQuestSel(len(gamestate.quests)))


async def teamvote_phase(client, message, gamestate):
    await message.channel.send(gamestate.t.teamvoteStr(gamestate.team_attempts, ", ".join(player.name for player in gamestate.current_party)))

    def votecheck(msg):
        if isinstance(msg.channel, DMChannel):
            if msg.author in voters:
                if gamestate.isCommand(msg.content, "yes") or gamestate.isCommand(msg.content, "no"):
                    return True
        elif gamestate.isCommand(msg.content, 'stop'):
            return True
        return False

    while gamestate.phase == Phase.TEAMVOTE:
        # wait for votes
        vc = 0
        rejectcounter = 0
        voteStr = gamestate.t.teamvoteResults + "\n"
        voters = [p.user for p in gamestate.players]
        pending_voters = [p.user for p in gamestate.players]
        num_voters = len(voters)
        # del voters[leader]   # enable to exclude leader from voting
        for voter in voters:
            await voter.send(gamestate.t.privateVoteInfo(gamestate.t.leaderInvocation(gamestate.players[gamestate.leader].name), gamestate.prefix + "yes", gamestate.prefix + "no"))
        send_delay_task = None
        with MsgQueue(client=client, check=votecheck) as msgqueue:
            while pending_voters:
                pmtrigger = await msgqueue.nextmsg()
                if pmtrigger.author in pending_voters:
                    vc += 1
                    pending_voters.remove(pmtrigger.author)
                    if send_delay_task != None:
                        send_delay_task.cancel()
                    author_name = gamestate.players_by_duid[pmtrigger.author.id].name
                    if gamestate.isCommand(pmtrigger.content, "yes"):
                        await confirm(pmtrigger)
                        voteStr += ":white_medium_square: "
                        if any(p.user.id == pmtrigger.author.id for p in gamestate.current_party):
                            voteStr += ":shield: "
                        voteStr += gamestate.t.votedApprove(author_name) + "\n"
                    elif gamestate.isCommand(pmtrigger.content, "no"):
                        await confirm(pmtrigger)
                        voteStr += ":black_medium_square: "
                        if any(p.user.id == pmtrigger.author.id for p in gamestate.current_party):
                            voteStr += ":shield: "
                        voteStr += gamestate.t.votedReject(author_name) + "\n"
                        rejectcounter += 1
                    elif gamestate.isCommand(pmtrigger.content, "stop"):
                        await confirm(pmtrigger)
                        await message.channel.send(gamestate.t.stopStr())
                        gamestate.phase = Phase.INIT
                        return
                    await message.channel.send(gamestate.t.teamvoteCount(author_name, vc, num_voters))
                    if len(pending_voters) > 0:
                        mentions = ', '.join(
                            [user.mention for user in pending_voters])
                        send_delay_task = asyncio.create_task(send_after_delay(
                            message.channel, gamestate.t.waitingFor(mentions)))

        # votes have been submitted
        if gamestate.leader == (len(gamestate.players)-1):
            gamestate.leader = 0
        else:
            gamestate.leader += 1

        if rejectcounter >= (len(gamestate.players) / 2):
            gamestate.team_attempts -= 1
            if gamestate.team_attempts == 0:
                voteStr += "\n" + gamestate.t.teamvoteEvilWins
                await message.channel.send(voteStr)
                gamestate.phase = Phase.GAMEOVER  # evil win state
            else:
                voteStr += "\n" + gamestate.t.teamvoteRejected
                await message.channel.send(voteStr)
                gamestate.phase = Phase.QUEST
        else:
            gamestate.team_attempts = 5  # reset passcount
            voteStr += "\n" + gamestate.t.teamvoteAccepted
            await message.channel.send(voteStr)
            gamestate.phase = Phase.PRIVATEVOTE


async def privatevote_phase(client, message, gamestate):
    while gamestate.phase == Phase.PRIVATEVOTE:
        fails = 0
        activeplayers = [p.user for p in gamestate.current_party]
        pending_players = [p.user for p in gamestate.current_party]
        namestring = " ".join(p.name for p in gamestate.current_party)

        def privatevotecheck(msg):
            if isinstance(msg.channel, DMChannel):
                if msg.author in activeplayers:
                    role = gamestate.players_by_duid[msg.author.id].role
                    # if (role.is_evil and role is not BRUTE) or (role is BRUTE and gamestate.current_quest <= 3):
                    if role.is_evil:
                        if role is LUNATIC:
                            if gamestate.isCommand(msg.content, "success"):
                                return False
                        if gamestate.isCommand(msg.content, "success") or gamestate.isCommand(msg.content, "fail"):
                            return True
                    if gamestate.isCommand(msg.content, "success"):
                        return True
            elif gamestate.isCommand(msg.content, 'stop'):
                return True
            return False

        await message.channel.send(gamestate.t.privatevoteStr(namestring))

        votecount = len(activeplayers)
        for voter in activeplayers:
            await voter.send(gamestate.t.privateVoteInfo(gamestate.t.quest, gamestate.prefix + "success", gamestate.prefix + "fail"))
        send_delay_task = None
        with MsgQueue(client=client, check=privatevotecheck) as msgqueue:
            while pending_players:
                pmtrigger = await msgqueue.nextmsg()
                if send_delay_task != None:
                    send_delay_task.cancel()
                pending_players.remove(pmtrigger.author)
                if gamestate.isCommand(pmtrigger.content, "success"):
                    await confirm(pmtrigger)
                    await gamestate.skin.send_image(gamestate.skin.success_choice, pmtrigger.channel)
                elif gamestate.isCommand(pmtrigger.content, "fail"):
                    await confirm(pmtrigger)
                    await gamestate.skin.send_image(gamestate.skin.fail_choice, pmtrigger.channel)
                    fails += 1
                if gamestate.isCommand(pmtrigger.content, "stop"):
                    await confirm(pmtrigger)
                    await message.channel.send(gamestate.t.stopStr())
                    gamestate.phase = Phase.INIT
                    return
                author_name = gamestate.players_by_duid[pmtrigger.author.id].name
                await message.channel.send(gamestate.t.privatevoteDone(author_name))
                if len(pending_players) > 0:
                    mentions = ", ".join(
                        [user.mention for user in pending_players])
                    send_delay_task = asyncio.create_task(send_after_delay(
                        message.channel, gamestate.t.waitingFor(mentions)))

        quest = gamestate.quests[gamestate.current_quest-1]
        if fails >= quest.required_fails:
            quest.winning_team = Team.EVIL
            resultText = gamestate.t.questFailed(fails)
            if gamestate.failed_quests == 2:
                for p in gamestate.players:
                    if p.role is REVEALER:
                        await message.channel.send(gamestate.t.revealerPM(p.user.mention))
        else:
            quest.winning_team = Team.GOOD
            resultText = gamestate.t.questSucceeded(fails)
        await message.channel.send(resultText, file=await gamestate.skin.get_votes_file(message.channel, votecount - fails, fails))

        if not gamestate.quest_selection:
            gamestate.current_quest += 1

        if (gamestate.succeeded_quests == 3 or gamestate.failed_quests == 3):
            gamestate.phase = Phase.GAMEOVER
        elif gamestate.enable_lady and (gamestate.completed_quests >= 2 and gamestate.completed_quests <= 4):
            gamestate.phase = Phase.LADY
        else:
            gamestate.phase = Phase.QUEST


async def lady_phase(client, message, gamestate):
    current_lady = gamestate.lady_players[-1]
    await gamestate.skin.send_image(gamestate.skin.lady, message.channel)
    await message.channel.send(gamestate.t.ladyInstructions(current_lady.user.mention))

    def ladycheck(msg):
        if msg.channel != message.channel:
            return False
        if gamestate.isCommand(msg.content, "lady") and msg.author == current_lady.user:
            return True
        return gamestate.isCommand(msg.content, "stop")
    while gamestate.phase == Phase.LADY:
        lady_message = await client.wait_for("message", check=ladycheck)
        if gamestate.isCommand(lady_message.content, "stop"):
            await confirm(lady_message)
            await message.channel.send(gamestate.t.stopStr())
            gamestate.phase = Phase.INIT
            return
        if not lady_message.mentions:
            await deny(lady_message)
            await message.channel.send(gamestate.t.noMentions)
            continue
        if len(lady_message.mentions) > 1:
            await deny(lady_message)
            await message.channel.send(gamestate.t.maxOneInspection)
            continue
        target_user = lady_message.mentions[0]
        if target_user == current_lady.user:
            await deny(lady_message)
            await message.channel.send(gamestate.t.noSelfInspect)
            continue
        if target_user in [p.user for p in gamestate.lady_players]:
            await deny(lady_message)
            await message.channel.send(gamestate.t.cantInspectPreviousLady)
            continue
        if not target_user.id in gamestate.players_by_duid:
            await deny(lady_message)
            await message.channel.send(gamestate.t.playerNotPlaying(target_user.display_name))
            continue
        await confirm(lady_message)
        target_player = gamestate.players_by_duid[target_user.id]
        if target_player.role is TRICKSTER:
            if current_lady.role.is_good or current_lady.role is OBERON:
                await gamestate.skin.send_image(gamestate.skin.loyalty_good, current_lady.user)
                await current_lady.user.send(gamestate.t.loyalArthur(target_player.name))
            else:
                await gamestate.skin.send_image(gamestate.skin.loyalty_evil, current_lady.user)
                await current_lady.user.send(gamestate.t.minionMordred(target_player.name))
        elif target_player.role is TROUBLEMAKER:
            await gamestate.skin.send_image(gamestate.skin.loyalty_evil, current_lady.user)
            await current_lady.user.send(gamestate.t.minionMordred(target_player.name))
        elif target_player.role.is_good:
            await gamestate.skin.send_image(gamestate.skin.loyalty_good, current_lady.user)
            await current_lady.user.send(gamestate.t.loyalArthur(target_player.name))
        else:
            await gamestate.skin.send_image(gamestate.skin.loyalty_evil, current_lady.user)
            await current_lady.user.send(gamestate.t.minionMordred(target_player.name))
        await message.channel.send(gamestate.t.loyaltyRevealed(target_player.name, current_lady.name))
        gamestate.lady_players.append(target_player)
        gamestate.phase = Phase.QUEST


async def send_after_delay(channel, message):
    await asyncio.sleep(20)
    await channel.send(message)


async def gameover_phase(client, message, gamestate):
    await gamestate.skin.send_board(gamestate, message.channel)
    if gamestate.succeeded_quests == 3:
        merlinPlayer = next(
            filter(lambda p: p.role == MERLIN, gamestate.players), None
        )
        merlin = None
        if merlinPlayer != None:
            merlin = merlinPlayer.user

        assassinPlayer = next(
            filter(lambda p: p.role == ASSASSIN, gamestate.players), None
        )
        if assassinPlayer == None:
            assassinPlayer = next(
                filter(lambda p: p.role == MORDRED, gamestate.players), None
            )
        if assassinPlayer == None:
            assassinPlayer = next(
                filter(lambda p: p.role.is_evil, gamestate.players), None
            )
        if assassinPlayer == None:
            await message.channel.send(gamestate.t.noMinions)
            await message.channel.send(gamestate.t.stopStr())
            gamestate.phase = Phase.INIT
            return
        assassin = assassinPlayer.user

        untrustworthyPlayer = next(
            filter(lambda p: p.role is UNTRUSTWORTHY_SERVANT, gamestate.players), None
        )
        if untrustworthyPlayer != None:
            untrustworthy = untrustworthyPlayer.user

            def untrustworthycheck(msg):
                if gamestate.isCommand(msg.content, 'recruit') and msg.author == assassin and len(msg.mentions) == 1:
                    return True
                elif gamestate.isCommand(msg.content, 'stop'):
                    return True
                return False
            await message.channel.send(gamestate.t.recruitPhase + "\n" + gamestate.t.recruitPrompt(assassin.mention))
            rec = await client.wait_for("message", check=add_channel_check(untrustworthycheck, message.channel))
            if gamestate.isCommand(rec.content, 'recruit'):
                await confirm(rec)
                recruit = rec.mentions[0]
                if untrustworthy.id == recruit.id:
                    await message.channel.send(gamestate.t.recruitSucceeded(untrustworthy.display_name))
                    assassin = untrustworthy
                else:
                    await message.channel.send(gamestate.t.recruitFailed(recruit.display_name))

        def assassincheck(msg):
            if gamestate.isCommand(msg.content, 'assassinate') and msg.author == assassin and len(msg.mentions) == 1:
                return True
            elif gamestate.isCommand(msg.content, 'stop'):
                return True
            return False
        await message.channel.send(gamestate.t.assassinPhase + "\n" + gamestate.t.assassinatePrompt(assassin.mention))
        ass = await client.wait_for("message", check=add_channel_check(assassincheck, message.channel))
        if gamestate.isCommand(ass.content, 'assassinate'):
            await confirm(ass)
            killedID = ass.mentions[0].id
            if merlin != None and merlin.id == killedID:
                await message.channel.send(gamestate.t.assassinateSucceeded)
                winning_team = Team.EVIL
            else:
                await message.channel.send(gamestate.t.assassinateFailed)
                winning_team = Team.GOOD
    elif gamestate.failed_quests == 3:
        await message.channel.send(gamestate.t.gameoverStr + "\n" + gamestate.t.evilWinsByQuests)
        winning_team = Team.EVIL
    else:
        await message.channel.send(gamestate.t.gameoverStr + "\n" + gamestate.t.evilWinsByFailure)
        winning_team = Team.EVIL
    roles_str = "\n".join(gamestate.t.roleReveal(player.name, gamestate.t[player.char.stringID])
                          for player in gamestate.players)
    await message.channel.send(roles_str)
    await message.channel.send(gamestate.t.stopStr())
    gamestate.phase = Phase.INIT


async def confirm(message):
    await message.add_reaction("✅")


async def deny(message):
    await message.add_reaction("⛔")


async def error(message):
    await message.add_reaction("❌")


async def warning(message):
    await message.add_reaction("⚠️")
