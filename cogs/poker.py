from decimal import Decimal
from datetime import datetime, timedelta

from typing import Optional

SUITS = ["H", "S", "C", "D"]
NUMBERS = tuple([str(i) for i in range(2, 11)] + ["J", "Q", "K", "A"])
DECK = tuple(((suit, number) for number in NUMBERS for suit in SUITS))

STATUS_IN = "in"
STATUS_ALL_IN = "all in"
STATUS_FOLDED = "folded"

MOVE_FOLD = "pk_fold"
MOVE_CHECK = "pk_check"
MOVE_CALL = "pk_call"
MOVE_RAISE = "pk_raise"
MOVE_ALL_IN = "pk_all_in"

ROUND_STAGES = [0, 3, 4, 5]

TIMEOUT_MINUTES = 10

CARD_TEMPLATE = ("┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐\n"
                 "│{n1}{s1}{b1}{b1}│ │{n2}{s2}{b2}{b2}│ │{n3}{s3}{b3}{b3}│ "
                 "│{n4}{s4}{b4}{b4}│ │{n5}{s5}{b5}{b5}│\n"
                 "│{b1}{b1}{b1}{b1}│ │{b2}{b2}{b2}{b2}│ │{b3}{b3}{b3}{b3}│ "
                 "│{b4}{b4}{b4}{b4}│ │{b5}{b5}{b5}{b5}│\n"
                 "└────┘ └────┘ └────┘ └────┘ └────┘")

# TODO: Currency precision
GAME_BOARD = """```Texas Hold'em
------------------------------------------------------------
Dealer:      {dealer}
Small blind: {small_blind} ({symbol}{sb_amount:.2f})
Big blind:   {big_blind} ({symbol}{bb_amount:.2f})

{cards}

Bet is currently {symbol}{bet:.2f}
It's {turn}'s turn! Would you like to {moves}?

------------------------------------------------------------
```"""


class PokerPlayer:
    def __init__(self, user_object, amount: Decimal):
        self.user_object = user_object
        self.amount = amount
        self.amount_in = Decimal(0)
        self._status = STATUS_IN

    @property
    def status(self) -> str:
        return self._status

    @status.setter
    def status(self, status: str) -> None:
        self._status = status

    @property
    def name(self) -> str:
        return self.user_object.display_name

    @property
    def discord_id(self):
        return self.user_object.id

    def move_in(self, amount: Decimal) -> None:
        # TODO: Check amounts?
        self.amount -= amount
        self.amount_in += amount


class PokerGame:
    def __init__(self, currency, host, round_limit: int, buy_in: Decimal):
        self.currency = currency
        self.host = host
        self.round = 1
        self.round_limit = round_limit
        self.buy_in = buy_in
        self.ongoing_game = False
        self.ongoing_round = False
        self._time_started = datetime.now()
        self._blind = buy_in / Decimal(100)
        self._deck = [card for card in DECK]
        self._in_play = [None, None, None, None, None]
        self.players = {}
        self.players_order = [host.id]
        self.dealer = 0
        self.small_blind = 1
        self.big_blind = 2
        self.starting_player = -1
        self.turn = -1  # Must be set at game time
        self.bet = Decimal(0)
        self.pot = Decimal(0)
        self.side_pots = {}  # TODO

    @property
    def num_folded(self):
        return len([p for p in self.players if p["status"] == STATUS_FOLDED])

    @property
    def stage(self):
        # 0  3  4    5
        # 0, 1, 2 or 3
        return ROUND_STAGES.index(len([c for c in self._in_play if c is None]))

    @property
    def _turn_player(self) -> PokerPlayer:
        return self.players[self.players_order[
            self.turn % len(self.players_order)]]

    @property
    def _dealer_player(self) -> PokerPlayer:
        return self.players[self.players_order[self.dealer]]

    @property
    def _small_blind_player(self) -> PokerPlayer:
        return self.players[self.players_order[self.small_blind]]

    @property
    def _big_blind_player(self) -> PokerPlayer:
        return self.players[self.players_order[self.big_blind]]

    def _get_fold_winner(self) -> Optional[PokerPlayer]:
        if self.num_folded < len(self.players_order) - 1:
            return None

        for player in self.players:
            if player.get_status() != STATUS_FOLDED:
                return player

    async def _print_game_screen(self, ctx) -> None:
        card_format = {}
        for n, card in enumerate(self._in_play, 1):
            if card is None:
                card_format["n{}".format(n)] = "X"
                card_format["s{}".format(n)] = "X"
                card_format["b{}".format(n)] = "X"
            else:
                card_format["n{}".format(n)] = card[1]  # Number
                card_format["s{}".format(n)] = card[0]  # Suite
                card_format["b{}".format(n)] = " "

        if self.bet == Decimal(0):
            moves = [MOVE_CHECK, MOVE_RAISE]
        else:
            moves = [MOVE_FOLD, MOVE_CALL, MOVE_RAISE]

        if len(moves) == 2:
            moves = " or ".join(moves)
        else:
            moves = ", ".join(moves[:-1]) + ", or {}".format(moves[-1])

        await ctx.send(GAME_BOARD.format(
            dealer=self._dealer_player.name,
            small_blind=self._small_blind_player.name,
            sb_amount=self.small_blind,
            big_blind=self._big_blind_player.name,
            bb_amount=self.big_blind,
            symbol=self.currency["symbol"],
            cards=CARD_TEMPLATE.format(**card_format),
            turn=self._turn_player.name,
            bet=self.bet,
            moves=moves))

    async def attempt_cancel(self, ctx) -> bool:
        if self._time_started < datetime.now() - timedelta(
                minutes=TIMEOUT_MINUTES):
            # Session has timed out
            await ctx.send("Game cancelled due to timeout.")
            return True

        if ctx.message.author.id != host.id:
            await ctx.send("You must be the host to cancel the game.")
            return False

        return True

    async def join(self, ctx) -> None:
        await ctx.trigger_typing()

        if self.ongoing_game:
            await ctx.send("Cannot join in the middle of a game.")
            return

        player = ctx.message.author

        if player.id in self.players:
            await ctx.send(
                "{} is already in the game.".format(player.display_name))
            return

        # TODO: Buy-in accounting

        self.players[player.id] = PokerPlayer(player, self.buy_in)
        self.players_order.append(player.id)

        await ctx.send("{} has joined the game!".format(
            self.players[player.id].name))

    async def start(self, ctx) -> None:
        """
        Start the round (not the turn!)
        """

        if self.ongoing_round:
            await ctx.send("Cannot start in the middle of a round.")
            return

        if ctx.message.author.id != self.host.id:
            await ctx.send("The host must start the round.")
            return

        if len(self.players_order) < 3:
            await ctx.send(
                "3 or more players must be joined in order to start the "
                "round.")

        self.ongoing_game = True
        self.ongoing_round = True
        self._time_started = datetime.now()  # Bump the timeout

        self._small_blind_player.move_in(self._blind / Decimal(2))
        self._big_blind_player.move_in(self._blind)

        self.bet = self._blind

        self.turn = (self.big_blind + 1) % len(self.players_order)

        await self._print_game_screen(ctx)

        # TODO: What to do here?

    async def _advance_turn(self, ctx) -> None:
        if self._get_fold_winner() is not None:
            await ctx.send("{name} won {symbol}{amount:.2f}".format(
                name=self._get_fold_winner().name,
                symbol=self.currency["symbol"],
                amount=self.pot))

            # TODO: MORE WIN CONDITION

            return

        self.turn += 1
        while self._turn_player.status in (STATUS_FOLDED, STATUS_ALL_IN):
            await ctx.send("{} is {}.".format(
                self._turn_player.name,
                self._turn_player.status))
            self.turn += 1

        # TODO: WHAT?

        await self._print_game_screen(ctx)

    async def try_move(self, ctx, move: str, amount: Optional[Decimal] = None) -> None:
        if self.game is None:
            await ctx.send("No poker game is in progress.")
            return

        if ctx.message.author.id not in self.players_order:
            await ctx.send("You are not a participant in this game.")
            return

        if ctx.message.author.id != self._turn_player.discord_id:
            await ctx.send("It is not your turn!")
            return

        if self.bet == 0 and move == MOVE_FOLD:
            await ctx.send("Why fold? There's no point.")
            return

        if self.bet == 0 and move == MOVE_CALL:
            move = MOVE_CHECK

        if self.bet > 0 and move == MOVE_CHECK:
            await ctx.send(
                "You can't check; the bet is already "
                "{symbol}{amount:.2f}".format(symbol=self.currency,
                                              amount=self.bet))
            return

        if self.bet >= self._turn_player.amount + self._turn_player.amount_in \
                and move in (MOVE_CALL, MOVE_RAISE):
            await ctx.send("You must go {}!".format(MOVE_ALL_IN))
            return

        # TODO: Make sure all players can pay raised amount?

        if move == MOVE_FOLD:
            self._turn_player.status = STATUS_FOLDED
            await ctx.send("{} folded!".format(self._turn_player.name))

        elif move == MOVE_CHECK:
            await ctx.send("{} checked.".format(self._turn_player.name))

        elif move == MOVE_CALL:
            self._turn_player.move_in(self.bet)
            await ctx.send("{} called.".format(self._turn_player.name))

        elif move == MOVE_RAISE:
            await ctx.send(
                "{} called the bet {} and raised by {:.2f} to {:2.f}!".format(
                    self._turn_player.name,
                    self.bet,
                    amount,
                    self.bet + amount
                ))

            self.bet = self.bet + amount
            self._turn_player.move_in(self.bet)

        elif move == MOVE_ALL_IN:
            all_in_amount = self._turn_player.amount

            await ctx.send("{} went all in with {:.2f}!".format(
                self._turn_player.name, all_in_amount))

            # TODO: POT LOGIC
            # TODO: AAAAAAH

            self._turn_player.move_in(all_in_amount)
            self._turn_player.status = STATUS_ALL_IN

        await self._advance_turn(ctx)


class Poker:
    def __init__(self, bot):
        self.bot = bot
        self.currency = self.bot.config.currency
        self.prec = self.currency["precision"]

        self.game: Optional[PokerGame] = None

    # Game management comments

    @commands.command(aliases=["pk_begin"])
    async def poker_begin(self, ctx, rounds=3, buy_in=20):
        """
        Begins a game of Texas Hold 'em for players to join.
        ?begin 10 200 starts a 10-round game with a buy-in of 200.
        """

        await ctx.trigger_typing()

        if self.game is not None:
            # Cannot begin unless no game is currently going
            await ctx.send("A poker game has already been started!")
            return

        if not isinstance(rounds, int) or rounds < 1:
            await ctx.send("A game must have at least one round.")
            return

        # TODO: Configurable buy-in minimum
        # TODO: Use currency precision
        if not isinstance(buy_in, int) or buy_in < 20:
            await ctx.send(
                "A game must have an integer buy-in of at least "
                "{}{:.2f}".format(self.currency["symbol"],
                                  Decimal(self.buy_in)))
            return

        self.game = PokerGame(
            self.currency, ctx.message.author, rounds, Decimal(buy_in))

        await ctx.send("{} has started a poker game!".format(
            ctx.message.author.display_name))

    @commands.command(aliases=["pk_cancel"])
    async def poker_cancel(self, ctx):
        """
        Cancels the game.
        """

        await ctx.trigger_typing()

        if self.game is None:
            # Cannot cancel unless a game is currently going
            await ctx.send("No poker game is in progress.")
            return

        # TODO: Figure out how to give player's money back in case of
        #  cancellation. What if cancellation/timeout happens in the middle
        #  of a round?

        result = await self.game.attempt_cancel(ctx)
        if result:
            self.game = None

    # Round management commands

    @commands.command(aliases=["pk_join"])
    async def poker_join(self, ctx):
        """
        Joins the round, paying the buy-in unless the player does not have
        enough money.
        """

        await ctx.trigger_typing()

        if self.game is None:
            # Cannot join if no game is in progress.
            await ctx.send("No poker game is in progress.")
            return

        await self.game.join(ctx)

    @commands.command(aliases=["pk_start"])
    async def poker_start(self, ctx):
        """
        Starts the round. Must be run by the host. At this point, players
        are locked in.
        """

        # TODO: If 2 people: dealer is small blind

        if self.game is None:
            await ctx.send("No poker game is in progress.")
            return

        await self.game.start(ctx)

    # Playing commands

    @commands.command(aliases=["pk_check"])
    async def poker_check(self, ctx):
        """
        Check
        """
        # Cannot check unless starting player (either first time or after a
        # round), or bet is currently

        await self.game.try_move(ctx, MOVE_CHECK)

    @commands.command(aliases=["pk_call"])
    async def poker_call(self, ctx):
        """
        Call
        """

        # Synonym for check if amount is currently 0
        # Cannot call if insufficient funds (have to do all_in)

        await self.game.try_move(ctx, MOVE_CALL)

    @commands.command(aliases=["pk_raise"])
    async def poker_raise(self, ctx, amount: str):
        """
        Raise
        """
        # Cannot raise if insufficient funds
        # Big blind can do it at end of the first round

        try:
            amount = Decimal(amount)
        except ValueError:
            await ctx.send("Cannot raise by invalid value {}. Try again.")
            return

        await self.game.try_move(ctx, MOVE_RAISE, amount)

    @commands.command(aliases=["pk_fold"])
    async def poker_fold(self):
        """
        Fold
        """
        # Cannot fold if bet is 0 (to make it fun)

        await self.game.try_move(ctx, MOVE_FOLD)
