import collections
__all__ = [ "MachineState", "OCF", "UnrecognisedInstructionError", "interrupt_response", "disassemble_instructions" ]

class UnrecognisedInstructionError(Exception):
    def __init__(self, inst):
        self.inst = inst
        if isinstance(inst, tuple):
            inst = "(" + ', '.join('0x{:X}'.format(i) for i in inst) + ")"
        else:
            inst = "0x{:X}".format(inst)
        super(UnrecognisedInstructionError, self).__init__("Unrecognised Instruction {}".format(inst))


# Actions which can be triggered at end of machine states

def JP(value=None, key=None, source=None):
    """Jump to the second parameter (an address)"""
    def _inner(state, *args):
        if isinstance(value, collections.Callable):
            target = value(state)
        elif value is not None:
            target = value
        elif source is not None:
            target = getattr(state.cpu.reg, source)
        elif key is not None:
            target = state.kwargs[key]
        elif len(args) > 0:
            target = args[0]
        else:
            target = state.kwargs["value"]
        state.cpu.reg.PC = target
    return _inner

def JR(value=None, key="value"):
    """Jump to PC plus the second parameter (an address) (or other source if provided)"""
    def _inner(state, *args):
        if isinstance(value, collections.Callable):
            target = value(state)
        elif value is not None:
            target = value
        elif len(args) > 0:
            target = args[0]
        else:
            target = state.kwargs[key]
        state.cpu.reg.PC += target
    return _inner

def LDr(reg, value=None, key="value"):
    """Load into the specified register"""
    def _inner(state, *args):
        if isinstance(value, collections.Callable):
            v = value(state, *args)
        elif value is not None:
            v = value
        elif len(args) > 0:
            v = args[0]
        else:
            v = state.kwargs[key]
        setattr(state.cpu.reg, reg, v)
    return _inner

def LDrs(r,s):
    """Load from the specified register into the specified register"""
    def _inner(state, *args):
        setattr(state.cpu.reg, r, getattr(state.cpu.reg, s))
    return _inner

def RRr(n,reg=None, value=None):
    """Load the value from the specified register and store as a key in the kwargs of the state"""
    def _inner(state, *args):
        if reg is not None:
            v = getattr(state.cpu.reg, reg)
        elif isinstance(value, collections.Callable):
            v = value(state, *args)
        elif value is not None:
            v = value
        elif len(args) > 0:
            v = args[0]
        else:
            raise Exception
        state.kwargs[n] = v
    return _inner

def EX(a=None, b=None):
    """Exchange the AF and AF' registers"""
    def _inner(state, *args):
        if a is None or b is None:
            state.cpu.reg.ex()
        else:
            tmp = getattr(state.cpu.reg, a)
            setattr(state.cpu.reg, a, getattr(state.cpu.reg, b))
            setattr(state.cpu.reg, b, tmp)
    return _inner

def EXX():
    """Exchange the working registers with their shadows"""
    def _inner(state, *args):
        state.cpu.reg.exx()
    return _inner

def add_register(r):
    """Load a value from the specified register and add it to the parameter"""
    def _inner(state, d, *args):
        return getattr(state.cpu.reg, r) + d
    return _inner

def subfrom(r="A"):
    """Subtract the value from the value in a register (A by default)."""
    def _inner(state, d, *args):
        return getattr(state.cpu.reg, r) - d
    return _inner

def do_each(*actions):
    """Perform a series of actions."""
    def _inner(state, *args):
        for action in actions:
            action(state, *args)
    return _inner

def inc(reg):
    """Increment a register"""
    def _inner(state, *args):
        if len(reg) % 2 == 0:
            setattr(state.cpu.reg, reg, (getattr(state.cpu.reg, reg) + 1)&0xFFFF)
        else:
            setattr(state.cpu.reg, reg, (getattr(state.cpu.reg, reg) + 1)&0xFF)
    return _inner

def dec(reg):
    """Decrement a register"""
    def _inner(state, *args):
        if len(reg)%2 == 0:
            setattr(state.cpu.reg, reg, (0xFFFF + getattr(state.cpu.reg, reg))&0xFFFF)
        else:
            setattr(state.cpu.reg, reg, (0xFF + getattr(state.cpu.reg, reg))&0xFF)
    return _inner

def inta(ds):
    """Acknowledge an interrupt, but ignore the data from the remote device"""
    def _inner(state, *args):
        try:
            next(ds)
        except:
            pass
    return _inner

def on_zero(reg, action):
    """Only take action if register is zero"""
    def _inner(state, *args):
        if getattr(state.cpu.reg, reg) == 0:
            action(state, *args)
    return _inner

def on_flag(flag, action):
    """Only take action is flag is set"""
    def _inner(state, *args):
        if state.cpu.reg.getflag(flag) == 1:
            action(state, *args)
    return _inner

def unless_flag(flag, action):
    """Only take action is flag is not set"""
    def _inner(state, *args):
        if state.cpu.reg.getflag(flag) == 0:
            action(state, *args)
    return _inner

def on_condition(condition , action):
    """Only take the action is the condition returns True"""
    def _inner(state, *args):
        if condition(state, *args):
            action(state, *args)
    return _inner

def force_flag(flag, value):
    """Clear a flag"""
    def _inner(state, *args):
        if isinstance(value, collections.Callable):
            v = value(state, *args)
        else:
            v = value
        if v == 0:
            state.cpu.reg.resetflag(flag)
        else:
            state.cpu.reg.setflag(flag)
    return _inner

def clear_flag(flag):
    """Clear a flag"""
    def _inner(state, *args):
        state.cpu.reg.resetflag(flag)
    return _inner

def early_abort():
    """Abort instruction"""
    def _inner(state, *args):
        while len(state.pipeline) > 1:
            state.pipeline.pop()
    return _inner

def set_flags(flags="SZ5-3---", key="value", source=None, value=None, dest=None):
    """Set the flags register according to the passed value"""
    def _inner(state, *args):
        if value is not None:
            if isinstance(value, collections.Callable):
                D = value(state, *args)
            else:
                D = value
        elif source is not None:
            D = getattr(state.cpu.reg, source)
        elif len(args) > 0:
            D = args[0]
        else:
            D = state.kwargs[key]
        d = D&0xFF

        if flags[0] == 'S':
            if (d >> 7)&0x1 == 1:
                state.cpu.reg.setflag('S')
            else:
                state.cpu.reg.resetflag('S')
        if flags[1] == 'Z':
            if (d == 0):
                state.cpu.reg.setflag('Z')
            else:
                state.cpu.reg.resetflag('Z')
        if flags[2] == '5':
            if (d >> 5)&0x1 == 1:
                state.cpu.reg.setflag('5')
            else:
                state.cpu.reg.resetflag('5')
        if flags[4] == '3':
            if (d >> 3)&0x1 == 1:
                state.cpu.reg.setflag('3')
            else:
                state.cpu.reg.resetflag('3')
        if flags[5] == '*':
            if state.cpu.iff2 == 1:
                state.cpu.reg.setflag('P')
            else:
                state.cpu.reg.resetflag('P')
        elif flags[5] == "V":
            if D > 127 or D < -128:
                state.cpu.reg.setflag("V")
            else:
                state.cpu.reg.resetflag("V")
        elif flags[5] == "P":
            p = d
            while p > 1:
                p = (p&0x1) ^ (p >> 1)
            if p == 0:
                state.cpu.reg.setflag("P")
            else:
                state.cpu.reg.resetflag("P")
        if flags[7] == 'C':
            if D > 255 or D < 0:
                state.cpu.reg.setflag("C")
            else:
                state.cpu.reg.resetflag("C")
        for n in range(0,7):
            if flags[7-n] == '1':
                state.cpu.reg.F = state.cpu.reg.F | (1 << n)
            elif flags[7-n] == '0':
                state.cpu.reg.F = state.cpu.reg.F & (0xFF - (1 << n))
        if key is not None:
            state.kwargs[key] = d
        if dest is not None:
            setattr(state.cpu.reg, dest, d)
    return _inner

def di():
    def _inner(state, *args):
        state.cpu.iff1 = 0
        state.cpu.iff2 = 0
    return _inner

def ei():
    def _inner(state, *args):
        state.cpu.iff1 = 1
        state.cpu.iff2 = 1
    return _inner

def im(m):
    def _inner(state, *args):
        state.cpu.interrupt_mode = m
    return _inner

def restore_iff():
    def _inner(state, *args):
        state.cpu.iff1 = state.cpu.iff2
    return _inner


def daa():
    def _inner(state, *args):
        A = state.cpu.reg.A
        C = (state.cpu.reg.F >> 0)&0x1
        H = (state.cpu.reg.F >> 4)&0x1
        N = (state.cpu.reg.F >> 1)&0x1

        if N == 0:
            F = 0
            if A&0xF > 9 or H != 0:
                A += 0x06
            if (A>>4) > 9 or C != 0:
                A += 0x60
                F = 0x01
        else:
            F = 0
            if (A&0xF) > 9 or H != 0:
                A -= 0x06
            if (A>>4) > 9 or C != 0:
                A -= 0x60
                F = 0x01
        A &= 0xFF
        F |= (N << 1)
        F |= (A&0xA8)
        if A == 0x00:
            F |= 0x40
        state.cpu.reg.A = A
        state.cpu.reg.F = F
    return _inner

# Machine States

class MachineState(object):
    def __init__(self):
        """Descendent classes may add extra parameters here, which are values set at decode time."""
        self.cpu          = None
        self.iter         = self.run()
        self.pipeline     = None
        self.args         = []
        self.kwargs       = {}
        self.return_value = None
        self.data_source  = None

    def setcpu(self, cpu):
        self.cpu = cpu
        return self

    def set_data_source(self, data_source):
        self.data_source = data_source
        return self

    def fetchlocked(self):
        """Returns True if a pipeline containing this machine state should block the state machine from
        starting a new OCF pipeline."""
        return False

    def run(self):
        """Should be a generator function. Don't yield values (they'll be ignored).
        Can set a return value for self.clock in self.return_value. In addition when
        this generator exits the value of self.args and self.kwargs will be transferred
        to the next state in the pipeline. This is useful for passing values on."""
        return
        yield None

    def clock(self, pipeline):
        self.pipeline = pipeline
        try:
            return next(self.iter)
        except StopIteration:
            self.pipeline.pop(0)
            if len(self.pipeline) > 0:
                self.pipeline[0].args   = self.args
                self.pipeline[0].kwargs = self.kwargs
            return self.return_value

def high_after_low(x,y):
    return ((x << 8) | y)

def OCF(prefix=None, data_source=None, extra=0):
    class _OCF(MachineState):
        """This state fetches an OP Code from memory and advances the PC in 4 t-cycles.
        Initialisation Parameters:
        - Optionally: 'prefix' for a multibyte op-code this will be prefixed to what is loaded
        - Optionally: 'data_source' an iterable to use to get data instead of reading the PC location in memory
        - Optionally: 'extra' extra clock cycles to wait for
        Args In:
        - None
        Args Out:
        - None
        Side Effects:
        - Increments PC
        - Decodes OP-Code and adds new machine states to the pipeline if required
        Returned Values:
        - None
        Time Taken:
        - 4 clock cycles, or more if decode indicates there should be."""

        def __init__(self):
            self.prefix      = prefix
            self.extra       = extra
            super(_OCF,self).__init__()
            self.data_source = data_source

        def fetchlocked(self):
            return True

        def run(self):
            PC = self.cpu.reg.PC
            yield

            if self.data_source is not None:
                try:
                    inst = next(self.data_source)
                except StopIteration:
                    inst = 0x00
            else:
                inst = self.cpu.membus.read(PC)

            if isinstance(self.prefix, int):
                inst = (self.prefix, inst)
            elif isinstance(self.prefix, tuple):
                inst = tuple(list(self.prefix) + [ inst ])
            self.cpu.most_recent_instruction = inst
            yield

            (extra_clocks, actions, states) = decode_instruction(inst)
            if self.data_source is None:
                self.cpu.reg.PC = PC + 1
            states = [ state().setcpu(self.cpu).set_data_source(self.data_source) for state in states ]
            yield

            for n in range(0,self.extra + extra_clocks-1):
                yield

            self.pipeline.extend(states)
            for action in actions:
                action(self)
            return
    return _OCF

def OD(compound=high_after_low, action=None, key="value", signed=False):
    class _OD(MachineState):
        """This state fetches an data byte from memory and advances the PC in 3 t-cycles.
        Initialisation Parameters:
        - Optionally: 'compound' a method that takes two parameters (new, old) used to combine
        the old value of 'value' with the new one.
        - Optionally: 'action' a method which takes a two parameters, the state and a single integer. 
        It will be called with the final value of 'value' as the last operation in the state. 
        - Optionally: 'signed', set to True if the input should be interpreted as 2's complement
        Args In:
        - Optionally: 'value' a single integer cascaded from a previous state
        Args Out:
        - 'value' : a integer cascaded to the next state
        Side Effects:
        - Increments PC, calls 'action'
        Returned Values:
        - None
        Time Taken:
        - 3 clock cycles"""

        def __init__(self):
            self.key      = key
            self.compound = compound
            self.action   = action
            self.signed   = signed
            super(_OD, self).__init__()

        def fetchlocked(self):
            return True

        def run(self):
            PC = self.cpu.reg.PC
            yield

            if self.data_source is None:
                D = self.cpu.membus.read(PC)
            else:
                try:
                    D = next(self.data_source)
                except StopIteration:
                    D = 0x00
            if signed and D >= 0x80:
                D = D - 0x100
            yield

            if self.data_source is None:
                self.cpu.reg.PC = PC + 1
            if self.key in self.kwargs and self.compound is not None:
                D = self.compound(D, self.kwargs[self.key])
            if self.action is not None:
                self.action(self, D)
            else:
                self.kwargs[self.key] = D
            return
    return _OD

def MR(address=None, indirect=None, compound=high_after_low, action=None, incaddr=True, verbose=False):
    class _MR(MachineState):
        """This state fetches a data byte from memory at a specified address (possibly using register indirect or indexed addressing):
        Initialisation Parameters:
        - Optionally: 'address' the address in memory to load from
        - Optionally: 'indirect' the name of the register to take the address from
        - Optionally: 'compound' a method that takes two parameters (new, old) used to combine
        the old value of 'value' with the new one.
        - Optionally: 'action' a method which takes a two parameters, the state and a single integer. 
        It will be called with the final value of 'value' as the last operation in the state. 
        Args In:
        - Optionally: 'value' a single integer cascaded from a previous state
        Args Out:
        - 'value' : the contents of the memory read, cascaded to the next state
        - 'address' : the address read from plus one
        Side Effects:
        - Calls 'action'
        Returned Values:
        - None
        Time Taken:
        - 3 clock cycles"""

        def __init__(self):
            self.address  = address
            self.indirect = indirect
            self.compound = compound
            self.action   = action
            self.incaddr  = incaddr
            self.verbose  = verbose
            super(_MR, self).__init__()

        def fetchlocked(self):
            return True

        def run(self):
            if self.address is None:
                if self.indirect is None:
                    if 'address' not in self.kwargs:
                        raise Exception("MR without either address of indirect specified")
                    else:
                        self.address = self.kwargs['address']
                        if self.verbose:
                            print("MR: Address 0x{:X} taken from kwargs[{}]".format(self.address, 'address'))
                else:
                    self.address = getattr(self.cpu.reg, self.indirect)
                    if self.verbose:
                        print("MR: Address 0x{:X} taken from register {}".format(self.address, self.indirect))
            yield

            D = self.cpu.membus.read(self.address)
            if self.verbose:
                print("MR: Data 0x{:X} read from address 0x{:X}".format(D, self.address))
            yield

            if 'value' in self.kwargs and self.compound is not None:
                D = self.compound(D, self.kwargs['value'])
                if self.verbose:
                    print("MR: Compound data with 0x{:X} to get 0x{:X}".format(self.kwargs['value'], D))
            if self.incaddr:
                self.kwargs['address'] = self.address + 1
                if self.verbose:
                    print("MR: Increment address to 0x{:X}".format(self.kwargs['address']))
            if self.action is not None:
                self.action(self, D)
                if self.verbose:
                    print("MR: Performing Action")
            else:
                self.kwargs['value'] = D
                if self.verbose:
                    print("MR: Setting 'value' in kwargs to 0x{:X}".format(D))
            return

    return _MR

def MW(address=None, indirect=None, value=None, source=None, action=None, extra=0, verbose=False):
    class _MW(MachineState):
        """This state writes a data byte to memory at a specified address (possibly using register indirect or indexed addressing):
        Initialisation Parameters:
        - Optionally: 'address' the address in memory to write to
        - Optionally: 'indirect' the name of the register to take the address from
        - Optionally: 'value' the value to write.
        - Optionally: 'source' a register from which to obtain the value to write. (if Neither value nor source is specified it will be cascaded in)
        - Optionally: 'action' an action to be taken at the end of the state
        - Optionally: 'extra' a number of extra t-cycles to wait for
        Args In:
        - Optionally: 'value' a single integer cascaded from a previous state
        - Optionally: 'address' a single integer cascaded from a previous state
        Args Out:
        - 'address': the address that was written to plus one (useful for 16-bit writes)
        Side Effects:
        - None
        Returned Values:
        - None
        Time Taken:
        - 3 clock cycles"""

        def __init__(self):
            self.address  = address
            self.indirect = indirect
            self.value    = value
            self.source   = source
            self.action   = action
            self.extra    = extra
            self.verbose  = verbose
            super(_MW, self).__init__()

        def fetchlocked(self):
            return True

        def run(self):
            if self.address is None:
                if self.indirect is None:
                    if 'address' not in self.kwargs:
                        raise Exception("MW without either address of indirect specified")
                    else:
                        self.address = self.kwargs['address']
                        if self.verbose:
                            print("MW: Address 0x{:X} from kwargs".format(self.address))
                else:
                    self.address = getattr(self.cpu.reg, self.indirect)
                    if self.verbose:
                        print("MW: Address 0x{:X} from register {}".format(self.address, self.indirect))
            yield

            if self.value is None:
                if self.source is None:
                    if 'value' not in self.kwargs:
                        raise Exception("MW without either value or source specified")
                    else:
                        self.value = self.kwargs['value']
                        if self.verbose:
                            print("MW: Value 0x{:X} from kwargs".format(self.value))
                else:
                    self.value = getattr(self.cpu.reg, self.source)
                    if self.verbose:
                        print("MW: Value 0x{:X} from register {}".format(self.value, self.source))
            elif isinstance(self.value, collections.Callable):
                self.value = self.value(self)
                if self.verbose:
                    print("MW: Value 0x{:X} from callable".format(self.value))
            yield

            self.cpu.membus.write(self.address, self.value)
            if self.verbose:
                print("MW: Writing 0x{:X} to 0x{:X}".format(self.value, self.address))
            self.kwargs['address'] = self.address + 1
            if self.verbose:
                print("MW: Increment Address to 0x{:X}".format(self.kwargs['address']))

            for n in range(0,self.extra):
                yield

            if self.action is not None:
                self.action(self, self.value)
                if self.verbose:
                    print("MW: Taking action")
            return
        
    return _MW

def SR(compound=high_after_low, action=None, extra=0):
    class _SR(MachineState):
        """This state fetches a data byte from memory at the top of the stack and increments the stack pointer:
        Initialisation Parameters:
        - Optionally: 'compound' a method that takes two parameters (new, old) used to combine
        the old value of 'value' with the new one.
        - Optionally: 'action' a method which takes a two parameters, the state and a single integer. 
        It will be called with the final value of 'value' as the last operation in the state. 
        - Optionally: 'extra' a number of extra t-cycles to wait for
        Args In:
        - Optionally: 'value' a single integer cascaded from a previous state
        Args Out:
        - 'value' : the contents of the memory read, cascaded to the next state
        Side Effects:
        - Calls 'action'
        - Increments SP
        Returned Values:
        - None
        Time Taken:
        - 3 clock cycles"""

        def __init__(self):
            self.compound = compound
            self.action   = action
            self.extra    = extra
            super(_SR, self).__init__()

        def fetchlocked(self):
            return True

        def run(self):
            self.address = self.cpu.reg.SP
            yield

            D = self.cpu.membus.read(self.address)
            yield

            for n in range(0,self.extra):
                yield

            if 'value' in self.kwargs and self.compound is not None:
                D = self.compound(D, self.kwargs['value'])
            self.kwargs['value'] = D
            self.cpu.reg.SP = self.cpu.reg.SP + 1
            if self.action is not None:
                self.action(self, D)
            return

    return _SR

def SW(source=None, key='value', extra=0, action=None):
    class _SW(MachineState):
        """This state decrements the stack pointer and writes a data byte to memory at the top of the stack:
        Initialisation Parameters:
        - Optionally: 'source' the register from which to take the value
        - Optionally: 'key' a key to use instead of 'value' to access the data to be written
        - Optionally: 'extra' a number of extra t-cycles to wait for
        Args In:
        - Possibly a value if none is specified by source
        Args Out:
        - None
        Side Effects:
        - Decrements SP
        Returned Values:
        - None
        Time Taken:
        - 3 clock cycles"""

        def __init__(self):
            self.source = source
            self.key    = key
            self.extra  = extra
            self.action = action
            super(_SW, self).__init__()

        def fetchlocked(self):
            return True

        def run(self):
            self.cpu.reg.SP = self.cpu.reg.SP - 1
            yield

            for n in range(0,self.extra):
                yield

            self.address = self.cpu.reg.SP
            yield

            if self.source is not None:
                D = getattr(self.cpu.reg, self.source)
            else:
                D = self.kwargs[self.key]

            self.cpu.membus.write(self.address, D)

            if self.action is not None:
                self.action(self, D)
            return

    return _SW

def IO(ticks, locked, transform=None, action=None, key="value"):
    class _IO(MachineState):
        """This state does nothing but take in and pass on args, apply transform to them and perform action
        Initialisation Parameters:
        - Mandatory : 'ticks', the time taken
        - Mandatory : 'locked', true if other states can't access memory whilst this is active
        - Optionally: 'transform' a method which will be called with this state and a cascaded in 'value' or a dictionary mapping args to methods
        - Optionally: 'action' a side effect called last thing in the state
        Args In:
        - Optionally: Any
        Args Out:
        - Anything passed in will be passed out
        Side Effects:
        - 'action' is called
        Returned Values:
        - None
        Time Taken:
        - variable"""

        def __init__(self):
            self.ticks  = ticks
            self.locked = locked
            self.transform = transform
            self.action   = action
            self.key      = key
            super(_IO, self).__init__()

        def fetchlocked(self):
            return self.locked

        def run(self):
            for key in self.kwargs:
                if isinstance(self.transform, collections.Callable) and key == self.key:
                    self.kwargs[key] = self.transform(self, self.kwargs[key])
                elif isinstance(self.transform, dict) and key in self.transform:
                    self.kwargs[key] = self.transform[key](self, self.kwargs[key])
            for n in range(0,self.ticks - 1):
                yield
            if isinstance(self.action, collections.Callable):
                self.action(self)
            return
        
    return _IO

def PR(high=None, low=None, action=None, dest=None):
    class _PR(MachineState):
        """This state fetches a data byte from an output port:
        Initialisation Parameters:
        - Optionally: 'high' the register from which the high address line byte should be taken
        - Optionally: 'low' the register from which the high address line byte should be taken
        - Optionally: 'dest' the name of the register to write to
        - Optionally: 'action' a method which takes a two parameters, the state and a single integer. 
        It will be called with the final value of 'value' as the last operation in the state. 
        Args In:
        - Optionally: 'value' a single integer cascaded from a previous state, used as the low byte of the address
        Args Out:
        - 'value' : the contents of the memory read, cascaded to the next state
        Side Effects:
        - Calls 'action'
        Returned Values:
        - None
        Time Taken:
        - 4 clock cycles"""

        def __init__(self):
            self.high   = high
            self.low    = low
            self.dest   = dest
            self.action = action
            super(_PR, self).__init__()

        def fetchlocked(self):
            return True

        def run(self):
            if self.low is not None:
                low = getattr(self.cpu.reg, self.low)
            else:
                low = (self.kwargs['value'])&0xFF

            if self.high is not None:
                high = getattr(self.cpu.reg, self.high)
            else:
                high = 0x00
            yield

            D = self.cpu.iobus.read(low, high)
            yield

            yield

            if self.dest is not None:
                setattr(self.cpu.reg, self.dest, D)

            self.kwargs['value'] = D

            if isinstance(self.action, collections.Callable):
                self.action(self, D)
            return

    return _PR

def PW(high=None, low=None, action=None, source=None):
    class _PW(MachineState):
        """This state writes a data byte to an output port:
        Initialisation Parameters:
        - Optionally: 'high' the register from which the high address line byte should be taken
        - Optionally: 'low' the register from which the high address line byte should be taken
        - Optionally: 'source' the name of the register to take the value from (otherwise from kwargs)
        - Optionally: 'action' a method which takes a two parameters, the state and a single integer. 
        It will be called with the final value of 'value' as the last operation in the state. 
        Args In:
        - Optionally: 'address' a single integer cascaded from a previous state, used as the low byte of the address
        - Optionally: 'value' a single integer cascaded from a previous state, used as the value to write
        Args Out:
        - 'value' : the contents of the memory read, cascaded to the next state
        Side Effects:
        - Calls 'action'
        Returned Values:
        - None
        Time Taken:
        - 4 clock cycles"""

        def __init__(self):
            self.high   = high
            self.low    = low
            self.source = source
            self.action = action
            super(_PW, self).__init__()

        def fetchlocked(self):
            return True

        def run(self):
            if self.low is not None:
                low = getattr(self.cpu.reg, self.low)
            else:
                low = (self.kwargs['address'])&0xFF

            if self.high is not None:
                high = getattr(self.cpu.reg, self.high)
            else:
                high = 0x00
            yield

            if self.source is not None:
                D = getattr(self.cpu.reg, self.source)
            else:
                D = (self.kwargs['value'])&0xFF
            yield

            self.cpu.iobus.write(low, high, D)
            yield

            self.kwargs['value'] = D

            if isinstance(self.action, collections.Callable):
                self.action(self, D)
            return

    return _PW

def ADC16(reg):
    """This instruction gets messy in the table, so we use this function to template it"""
    return [ RRr('value',   'HL'),
             RRr('summand', reg),
             force_flag('H', lambda  state : 1 if (((state.kwargs['summand']>>8)&0xF)+((state.kwargs['value']>>8)&0xF)+
                                                       (((state.kwargs['summand']&0xFF) + (state.kwargs['value']&0xFF)
                                                             +state.cpu.reg.getflag('C'))>>8) > 0xF) else 0),
             LDr('HL', value=lambda state : (state.kwargs['summand'] + state.kwargs['value'] + state.cpu.reg.getflag('C'))&0xFFFF),
             set_flags("S-5-3V0C", value=lambda state : (state.kwargs['summand'] >> 8) + (state.kwargs['value']>>8) +
                           (((state.kwargs['summand']&0xFF) + (state.kwargs['value']&0xFF) + state.cpu.reg.getflag('C'))>>8)),
             force_flag('Z', value=lambda state : 1 if state.cpu.reg.HL == 0x0000 else 0),]

def SBC16(reg):
    """This instruction gets messy in the table, so we use this function to template it"""
    return [ RRr('value',   'HL'),
             RRr('summand', value=lambda state : (-getattr(state.cpu.reg,reg))&0xFFFF),
             force_flag('H', lambda  state : 1 if (((state.kwargs['summand']>>8)&0xF)+((state.kwargs['value']>>8)&0xF)+
                                                       (((state.kwargs['summand']&0xFF) + (state.kwargs['value']&0xFF)
                                                             -state.cpu.reg.getflag('C'))>>8) > 0xF) else 0),
             LDr('HL', value=lambda state : (state.kwargs['summand'] + state.kwargs['value'] - state.cpu.reg.getflag('C'))&0xFFFF),
             set_flags("S-5-3V1C", value=lambda state : (state.kwargs['summand'] >> 8) + (state.kwargs['value']>>8) +
                           (((state.kwargs['summand']&0xFF) + (state.kwargs['value']&0xFF) - state.cpu.reg.getflag('C'))>>8)),
             force_flag('Z', value=lambda state : 1 if state.cpu.reg.HL == 0x0000 else 0),]

def RLC(reg=None, key='value'):
    """This instruction gets a little messy in the table, so this helps simplify it."""
    if reg is not None:
        return set_flags("--503-0C", value=lambda state : (getattr(state.cpu.reg,reg) << 1) | (getattr(state.cpu.reg,reg) >> 7), dest=reg)
    else:
        return set_flags("--503-0C", value=lambda state,v : (v << 1) | (v >> 7), key=key)

def RL(reg=None, key='value'):
    """This instruction gets a little messy in the table, so this helps simplify it."""
    if reg is not None:
        return set_flags("--503-0C", value=lambda state : (getattr(state.cpu.reg,reg) << 1) | (state.cpu.reg.getflag('C')), dest=reg)
    else:
        return set_flags("--503-0C", value=lambda state,v : (v << 1) | (state.cpu.reg.getflag('C')), key=key)

def RRC(reg=None, key='value'):
    """This instruction gets a little messy in the table, so this helps simplify it."""
    if reg is not None:
        return set_flags("--503-0C", value=lambda state : (getattr(state.cpu.reg,reg) >> 1) | ((getattr(state.cpu.reg,reg)&0x01) << 7) | ((getattr(state.cpu.reg,reg)&0x01) << 8), dest=reg)
    else:
        return set_flags("--503-0C", value=lambda state,v : (v >> 1) | ((v&0x01) << 7) | ((v&0x01) << 8), key=key)

def RR(reg=None, key='value'):
    """This instruction gets a little messy in the table, so this helps simplify it."""
    if reg is not None:
        return set_flags("--503-0C", value=lambda state : (getattr(state.cpu.reg,reg) >> 1) | (state.cpu.reg.getflag('C') << 7) | ((getattr(state.cpu.reg,reg)&0x01) << 8), dest=reg)
    else:
        return set_flags("--503-0C", value=lambda state,v : (v >> 1) | (state.cpu.reg.getflag('C') << 7) | ((v&0x01) << 8), key=key)

def SLA(reg=None, key='value'):
    """This instruction gets a little messy in the table, so this helps simplify it."""
    if reg is not None:
        return set_flags("--503-0C", value=lambda state : (getattr(state.cpu.reg,reg) << 1), dest=reg)
    else:
        return set_flags("--503-0C", value=lambda state,v : (v << 1), key=key)

def SRA(reg=None, key='value'):
    """This instruction gets a little messy in the table, so this helps simplify it."""
    if reg is not None:
        return set_flags("--503-0C", value=lambda state : (getattr(state.cpu.reg,reg) >> 1) | (getattr(state.cpu.reg,reg)&0x80) | ((getattr(state.cpu.reg,reg)&0x01) << 8), dest=reg)
    else:
        return set_flags("--503-0C", value=lambda state,v : (v >> 1) | (v&0x80) | ((v&0x01) << 8), key=key)

def SL1(reg=None, key='value'):
    """This instruction gets a little messy in the table, so this helps simplify it."""
    if reg is not None:
        return set_flags("--503-0C", value=lambda state : (getattr(state.cpu.reg,reg) << 1) | 0x01, dest=reg)
    else:
        return set_flags("--503-0C", value=lambda state,v : (v << 1) | 0x01, key=key)

def SRL(reg=None, key='value'):
    """This instruction gets a little messy in the table, so this helps simplify it."""
    if reg is not None:
        return set_flags("--503-0C", value=lambda state : (getattr(state.cpu.reg,reg) >> 1) | ((getattr(state.cpu.reg,reg)&0x01) << 8), dest=reg)
    else:
        return set_flags("--503-0C", value=lambda state,v : (v >> 1) | ((v&0x01) << 8), key=key)

def BIT(n, reg=None):
    """This instruction gets a little messy in the table, so this helps simplify it."""
    if reg is not None:
        return set_flags("SZ513P0-", value=lambda state : (getattr(state.cpu.reg,reg)&(1 << n)))
    else:
        return set_flags("SZ513P0-", value=lambda state,v : (v&(1 << n)))

def RES(n, reg=None, key="value"):
    """This instruction gets a little messy in the table, so this helps simplify it."""
    if reg is not None:
        return LDr(reg, value=lambda state : (getattr(state.cpu.reg,reg)&(0xFF - (1 << n))))
    else:
        return RRr(key, value=lambda state,v : (v&(0xFF - (1 << n))))

def SET(n, reg=None, key="value"):
    """This instruction gets a little messy in the table, so this helps simplify it."""
    if reg is not None:
        return LDr(reg, value=lambda state : (getattr(state.cpu.reg,reg)|(1 << n)))
    else:
        return RRr(key, value=lambda state,v : (v|(1 << n)))

INSTRUCTION_STATES = {
    # Single bytes opcodes
    0x00 : (0, [],                  [], "NOP", 1),
    0x01 : (0, [],                  [ OD(), OD(action=LDr('BC')) ], "LD BC,nn", 3),
    0x02 : (0, [],                  [ MW(indirect="BC", source="A") ], "LD (BC),A", 1),
    0x03 : (0, [ LDr('BC', value=lambda state : (state.cpu.reg.BC + 1)&0xFFFF) ],
                                    [], "INC BC", 1),
    0x04 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.B)&0xF)+1 > 0xF) else 0),
                 set_flags("SZ5-3V0-", value=lambda state : state.cpu.reg.B + 1, key="value"), LDr('B') ],
                                    [], "INC B", 1),
    0x05 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.B)&0xF)-1 < 0x0) else 0),
                 set_flags("SZ5-3V1-", value=lambda state : state.cpu.reg.B - 1, key="value"), LDr('B') ],
                                    [], "DEC B", 1),
    0x06 : (0, [],                  [ OD(action=LDr('B')), ], "LD B,n", 2),
    0x07 : (0, [ RLC("A") ],        [], "RLCA", 1),
    0x08 : (0, [ EX() ],            [], "EX AF,AF'", 1),
    0x09 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.B)&0xF)+((state.cpu.reg.H)&0xF)+((state.cpu.reg.C+state.cpu.reg.L)>>8) > 0xF) else 0),
                 set_flags("--5-3-0C", value=lambda state : state.cpu.reg.B + state.cpu.reg.H + ((state.cpu.reg.C+state.cpu.reg.L)>>8)),
                 LDr('HL', value=lambda state : (state.cpu.reg.HL + state.cpu.reg.BC)&0xFFFF) ],
                                    [ IO(4, True), IO(3, True) ], "ADD HL,BC", 1),
    0x0B : (0, [ LDr('BC', value=lambda state : (state.cpu.reg.BC - 1)&0xFFFF) ],
                                    [], "DEC BC", 1),
    0x0C : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.C)&0xF)+1 > 0xF) else 0),
                 set_flags("SZ5-3V0-", value=lambda state : state.cpu.reg.C + 1, key="value"), LDr('C') ],
                                    [], "INC C", 1),
    0x0D : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.C)&0xF)-1 < 0x0) else 0),
                 set_flags("SZ5H3V1-", value=lambda state : state.cpu.reg.C - 1, key="value"), LDr('C') ],
                                    [], "DEC C", 1),
    0x0E : (0, [],                  [ OD(action=LDr('C')), ], "LD C,n", 2),
    0x0F : (0, [ set_flags("--503-0C", value=lambda state : (state.cpu.reg.A >> 1) | ((state.cpu.reg.A&0x01) << 7) | ((state.cpu.reg.A&0x01) << 8), dest="A") ],
                                    [], "RRCA", 1),
    0x0A : (0, [],                  [ MR(indirect="BC", action=LDr("A")) ], "LD A,(BC)", 1),
    0x10 : (1, [],                  [ OD(signed=True,
                                         action=do_each(LDr("B", value=lambda state,v: (state.cpu.reg.B-1)&0xFF),
                                                        on_condition(lambda state,v : (state.cpu.reg.B == 0x00), early_abort()),
                                                        RRr("value"))),
                                      IO(5, True, action=JR()) ], "DJNZ n", 2),
    0x11 : (0, [],                  [ OD(), OD(action=LDr('DE')) ], "LD DE,nn", 3),
    0x12 : (0, [],                  [ MW(indirect="DE", source="A") ], "LD (DE),A", 1),
    0x13 : (0, [ LDr('DE', value=lambda state : (state.cpu.reg.DE + 1)&0xFFFF) ],
                                    [], "INC DE", 1),
    0x14 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.D)&0xF)+1 > 0xF) else 0),
                 set_flags("SZ5-3V0-", value=lambda state : state.cpu.reg.D + 1, key="value"), LDr('D') ],
                                    [], "INC D", 1),
    0x15 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.D)&0xF)-1 < 0x0) else 0),
                 set_flags("SZ5H3V1-", value=lambda state : state.cpu.reg.D - 1, key="value"), LDr('D') ],
                                    [], "DEC D", 1),
    0x16 : (0, [],                  [ OD(action=LDr('D')), ], "LD D,n", 2),
    0x17 : (0, [ RL("A") ],         [], "RLA", 1),
    0x18 : (0, [],                  [ OD(signed=True), IO(5, True, action=JR()) ], "JR n", 2),
    0x19 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.D)&0xF)+((state.cpu.reg.H)&0xF)+((state.cpu.reg.E+state.cpu.reg.L)>>8) > 0xF) else 0),
                 set_flags("--5-3-0C", value=lambda state : state.cpu.reg.D + state.cpu.reg.H + ((state.cpu.reg.E+state.cpu.reg.L)>>8)),
                 LDr('HL', value=lambda state : (state.cpu.reg.HL + state.cpu.reg.DE)&0xFFFF) ],
                                    [ IO(4, True), IO(3, True) ], "ADD HL,DE", 1),
    0x1B : (0, [ LDr('DE', value=lambda state : (state.cpu.reg.DE - 1)&0xFFFF) ],
                                    [], "DEC DE", 1),
    0x1A : (0, [],                  [ MR(indirect="DE", action=LDr("A")) ], "LD A,(DE)", 1),
    0x1C : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.E)&0xF)+1 > 0xF) else 0),
                 set_flags("SZ5-3V0-", value=lambda state : state.cpu.reg.E + 1, key="value"), LDr('E') ],
                                    [], "INC E", 1),
    0x1D : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.E)&0xF)-1 < 0x0) else 0),
                 set_flags("SZ5H3V1-", value=lambda state : state.cpu.reg.E - 1, key="value"), LDr('E') ],
                                    [], "DEC E", 1),
    0x1E : (0, [],                  [ OD(action=LDr('E')), ], "LD E,n", 2),
    0x1F : (0, [ RR("A") ],         [], "RRA", 1),
    0x20 : (0, [],                  [ OD(signed=True, action=do_each(RRr("value"), on_flag("Z", early_abort()))),
                                      IO(5, True, action=JR()) ], "JR NZ,n", 2),
    0x21 : (0, [],                  [ OD(), OD(action=LDr('HL')) ], "LD HL,nn", 3),
    0x22 : (0, [],                  [ OD(key="address"),
                                        OD(key="address",
                                        compound=high_after_low),
                                        MW(source="L"), MW(source="H") ], "LD (nn),HL", 3),
    0x23 : (0, [ LDr('HL', value=lambda state : (state.cpu.reg.HL + 1)&0xFFFF) ],
                                    [], "INC HL", 1),
    0x24 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.H)&0xF)+1 > 0xF) else 0),
                 set_flags("SZ5-3V0-", value=lambda state : state.cpu.reg.H + 1, key="value"), LDr('H') ],
                                    [], "INC H", 1),
    0x25 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.H)&0xF)-1 < 0x0) else 0),
                 set_flags("SZ5H3V1-", value=lambda state : state.cpu.reg.H - 1, key="value"), LDr('H') ],
                                    [], "DEC H", 1),
    0x26 : (0, [],                  [ OD(action=LDr('H')), ], "LD H,n", 2),
    0x27 : (0, [ daa() ],                  [], "DAA", 2),
    0x28 : (0, [],                  [ OD(signed=True, action=do_each(RRr("value"), unless_flag("Z", early_abort()))),
                                      IO(5, True, action=JR()) ], "JR Z,n", 2),
    0x29 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.H)&0xF)+((state.cpu.reg.H)&0xF)+((state.cpu.reg.L+state.cpu.reg.L)>>8) > 0xF) else 0),
                 set_flags("--5-3-0C", value=lambda state : state.cpu.reg.H + state.cpu.reg.H + ((state.cpu.reg.L+state.cpu.reg.L)>>8)),
                 LDr('HL', value=lambda state : (state.cpu.reg.HL + state.cpu.reg.HL)&0xFFFF) ],
                                    [ IO(4, True), IO(3, True) ], "ADD HL,HL", 1),
    0x2A : (0, [],                  [ OD(key="address"),
                                      OD(key="address", compound=high_after_low),
                                      MR(action=LDr('L')), MR(action=LDr('H')) ], "LD HL,(nn)", 3),
    0x2B : (0, [ LDr('HL', value=lambda state : (state.cpu.reg.HL - 1)&0xFFFF) ],
                                    [], "DEC HL", 1),
    0x2C : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.L)&0xF)+1 > 0xF) else 0),
                 set_flags("SZ5-3V0-", value=lambda state : state.cpu.reg.L + 1, key="value"), LDr('L') ],
                                    [], "INC L", 1),
    0x2D : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.L)&0xF)-1 < 0x0) else 0),
                 set_flags("SZ5H3V1-", value=lambda state : state.cpu.reg.L - 1, key="value"), LDr('L') ],
                                    [], "DEC L", 1),
    0x2E : (0, [],                  [ OD(action=LDr('L')), ], "LD L,n"),
    0x2F : (0, [ set_flags("--*1*-1-", source='A'), LDr('A', value=lambda state : (~(state.cpu.reg.A))&0xFF) ],
                                    [], "CPL", 1),
    0x30 : (0, [],                  [ OD(signed=True, action=do_each(RRr("value"), on_flag("C", early_abort()))),
                                      IO(5, True, action=JR()) ], "JR NC,n", 2),
    0x31 : (0, [],                  [ OD(), OD(action=LDr('SP')) ], "LD SP,nn", 3),
    0x32 : (0, [],                  [ OD(key="address"), OD(compound=high_after_low,key="address"),
                                          MW(source="A") ], "LD (nn),A", 3),
    0x33 : (0, [ LDr('SP', value=lambda state : (state.cpu.reg.SP + 1)&0xFFFF) ],
                                    [], "INC SP", 1),
    0x34 : (0, [],                  [ MR(indirect="HL",
                                        action=do_each(force_flag('H', lambda  state,v : 1 if ((v&0xF)+1 > 0xF) else 0),
                                                      set_flags("SZ5-3V0-",
                                                        value=lambda state, v : v+1,
                                                        key="value"))),
                                      MW(indirect="HL" )], "INC (HL)", 1),
    0x35 : (0, [],                  [ MR(indirect="HL",
                                        action=do_each(
                                            force_flag('H', lambda  state,v : 1 if ((v&0xF)-1 < 0x0) else 0),
                                            set_flags("SZ5H3V1-",
                                                        value=lambda state, v : v-1,
                                                        key="value"))),
                                      MW(indirect="HL" )], "DEC (HL)", 1),
    0x36 : (0, [],                  [ OD(), MW(indirect="HL") ], "LD (HL),n", 2),
    0x37 : (0, [ LDr('F', value=lambda state : (state.cpu.reg.F&0xC4)|(state.cpu.reg.A&0x28)|(0x01)) ],
                                    [], "SCF", 1),
    0x38 : (0, [],                  [ OD(signed=True, action=do_each(RRr("value"), unless_flag("C", early_abort()))),
                                      IO(5, True, action=JR()) ], "JR C,n", 2),
    0x39 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.SPH)&0xF)+((state.cpu.reg.H)&0xF)+((state.cpu.reg.SPL+state.cpu.reg.L)>>8) > 0xF) else 0),
                 set_flags("--5-3-0C", value=lambda state : state.cpu.reg.SPH + state.cpu.reg.H + ((state.cpu.reg.SPL+state.cpu.reg.L)>>8)),
                 LDr('HL', value=lambda state : (state.cpu.reg.SP + state.cpu.reg.HL)&0xFFFF) ],
                                    [ IO(4, True), IO(3, True) ], "ADD HL,SP", 1),
    0x3B : (0, [ LDr('SP', value=lambda state : (state.cpu.reg.SP - 1)&0xFFFF) ],
                                    [], "DEC SP", 1),
    0x3C : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)+1 > 0xF) else 0),
                 set_flags("SZ5-3V0-", value=lambda state : state.cpu.reg.A + 1, key="value"), LDr('A') ],
                                    [], "INC A", 1),
    0x3D : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)-1 < 0x0) else 0),
                 set_flags("SZ5H3V1-", value=lambda state : state.cpu.reg.A - 1, key="value"), LDr('A') ],
                                    [], "DEC A", 1),
    0x3A : (0, [],                  [ OD(key="address"), OD(compound=high_after_low,key="address"),
                                          MR(action=LDr("A")) ], "LD A,(nn)", 3),
    0x3E : (0, [],                  [ OD(action=LDr('A')), ], "LD A,n", 2),
    0x3F : (0, [ LDr('F', value=lambda state : (state.cpu.reg.F&0xEC)|(~state.cpu.reg.F&0x11)) ],
                                    [], "CCF", 1),
    0x40 : (0, [ LDrs('B', 'B'), ], [], "LD B,B", 1),
    0x41 : (0, [ LDrs('B', 'C'), ], [], "LD B,C", 1),
    0x42 : (0, [ LDrs('B', 'D'), ], [], "LD B,D", 1),
    0x43 : (0, [ LDrs('B', 'E'), ], [], "LD B,E", 1),
    0x44 : (0, [ LDrs('B', 'H'), ], [], "LD B,H", 1),
    0x45 : (0, [ LDrs('B', 'L'), ], [], "LD B,L", 1),
    0x46 : (0, [],                  [ MR(indirect="HL", action=LDr("B")) ], "LD B,(HL)", 1),
    0x47 : (0, [ LDrs('B', 'A'), ], [], "LD B,A", 1),
    0x48 : (0, [ LDrs('C', 'B'), ], [], "LD C,B", 1),
    0x49 : (0, [ LDrs('C', 'C'), ], [], "LD C,C", 1),
    0x4A : (0, [ LDrs('C', 'D'), ], [], "LD C,D", 1),
    0x4B : (0, [ LDrs('C', 'E'), ], [], "LD C,E", 1),
    0x4C : (0, [ LDrs('C', 'H'), ], [], "LD C,H", 1),
    0x4D : (0, [ LDrs('C', 'L'), ], [], "LD C,L", 1),
    0x4E : (0, [],                  [ MR(indirect="HL", action=LDr("C")) ], "LD C,(HL)", 1),
    0x4F : (0, [ LDrs('C', 'A'), ], [], "LD C,A", 1),
    0x50 : (0, [ LDrs('D', 'B'), ], [], "LD D,B", 1),
    0x51 : (0, [ LDrs('D', 'C'), ], [], "LD D,C", 1),
    0x52 : (0, [ LDrs('D', 'D'), ], [], "LD D,D", 1),
    0x53 : (0, [ LDrs('D', 'E'), ], [], "LD D,E", 1),
    0x54 : (0, [ LDrs('D', 'H'), ], [], "LD D,H", 1),
    0x55 : (0, [ LDrs('D', 'L'), ], [], "LD D,L", 1),
    0x56 : (0, [],                  [ MR(indirect="HL", action=LDr("D")) ], "LD D,(HL)", 1),
    0x57 : (0, [ LDrs('D', 'A'), ], [], "LD D,A", 1),
    0x58 : (0, [ LDrs('E', 'B'), ], [], "LD E,B", 1),
    0x59 : (0, [ LDrs('E', 'C'), ], [], "LD E,C", 1),
    0x5A : (0, [ LDrs('E', 'D'), ], [], "LD E,D", 1),
    0x5B : (0, [ LDrs('E', 'E'), ], [], "LD E,E", 1),
    0x5C : (0, [ LDrs('E', 'H'), ], [], "LD E,H", 1),
    0x5D : (0, [ LDrs('E', 'L'), ], [], "LD E,L", 1),
    0x5E : (0, [],                  [ MR(indirect="HL", action=LDr("E")) ], "LD E,(HL)", 1),
    0x5F : (0, [ LDrs('E', 'A'), ], [], "LD E,A", 1),
    0x60 : (0, [ LDrs('H', 'B'), ], [], "LD H,B", 1),
    0x61 : (0, [ LDrs('H', 'C'), ], [], "LD H,C", 1),
    0x62 : (0, [ LDrs('H', 'D'), ], [], "LD H,D", 1),
    0x63 : (0, [ LDrs('H', 'E'), ], [], "LD H,E", 1),
    0x64 : (0, [ LDrs('H', 'H'), ], [], "LD H,H", 1),
    0x65 : (0, [ LDrs('H', 'L'), ], [], "LD H,L", 1),
    0x66 : (0, [],                  [ MR(indirect="HL", action=LDr("H")) ], "LD H,(HL)", 1),
    0x67 : (0, [ LDrs('H', 'A'), ], [], "LD H,A", 1),
    0x68 : (0, [ LDrs('L', 'B'), ], [], "LD L,B", 1),
    0x69 : (0, [ LDrs('L', 'C'), ], [], "LD L,C", 1),
    0x6A : (0, [ LDrs('L', 'D'), ], [], "LD L,D", 1),
    0x6B : (0, [ LDrs('L', 'E'), ], [], "LD L,E", 1),
    0x6C : (0, [ LDrs('L', 'H'), ], [], "LD L,H", 1),
    0x6D : (0, [ LDrs('L', 'L'), ], [], "LD L,L", 1),
    0x6E : (0, [],                  [ MR(indirect="HL", action=LDr("L")) ], "LD L,(HL)", 1),
    0x6F : (0, [ LDrs('L', 'A'), ], [], "LD L,A", 1),
    0x70 : (0, [],                  [ MW(indirect="HL", source="B") ], "LD (HL),B", 1),
    0x71 : (0, [],                  [ MW(indirect="HL", source="C") ], "LD (HL),C", 1),
    0x72 : (0, [],                  [ MW(indirect="HL", source="D") ], "LD (HL),D", 1),
    0x73 : (0, [],                  [ MW(indirect="HL", source="E") ], "LD (HL),E", 1),
    0x74 : (0, [],                  [ MW(indirect="HL", source="H") ], "LD (HL),H", 1),
    0x75 : (0, [],                  [ MW(indirect="HL", source="L") ], "LD (HL),L", 1),
    0x76 : (0, [ on_condition(lambda state : not state.cpu.int, dec("PC")) ], [], "HALT", 1),
    0x77 : (0, [],                  [ MW(indirect="HL", source="A") ], "LD (HL),A", 1),
    0x78 : (0, [ LDrs('A', 'B'), ], [], "LD A,B", 1),
    0x79 : (0, [ LDrs('A', 'C'), ], [], "LD A,C", 1),
    0x7A : (0, [ LDrs('A', 'D'), ], [], "LD A,D", 1),
    0x7B : (0, [ LDrs('A', 'E'), ], [], "LD A,E", 1),
    0x7C : (0, [ LDrs('A', 'H'), ], [], "LD A,H", 1),
    0x7D : (0, [ LDrs('A', 'L'), ], [], "LD A,L", 1),
    0x7E : (0, [],                  [ MR(indirect="HL", action=LDr("A")) ], "LD A, (HL)", 1),
    0x7F : (0, [ LDrs('A', 'A'), ], [], "LD A,A", 1),
    0x80 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)+((state.cpu.reg.B)&0xF) > 0xF) else 0),
                 set_flags("SZ5-3V0C", value=lambda state : state.cpu.reg.A + state.cpu.reg.B, key="value"),
                 LDr('A') ],        [], "ADD B", 1),
    0x81 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)+((state.cpu.reg.C)&0xF) > 0xF) else 0),
                 set_flags("SZ5H3V0C", value=lambda state : state.cpu.reg.A + state.cpu.reg.C, key="value"),
                 LDr('A') ],        [], "ADD C", 1),
    0x82 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)+((state.cpu.reg.D)&0xF) > 0xF) else 0),
                 set_flags("SZ5H3V0C", value=lambda state : state.cpu.reg.A + state.cpu.reg.D, key="value"),
                 LDr('A') ],        [], "ADD D", 1),
    0x83 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)+((state.cpu.reg.E)&0xF) > 0xF) else 0),
                 set_flags("SZ5H3V0C", value=lambda state : state.cpu.reg.A + state.cpu.reg.E, key="value"),
                 LDr('A') ],        [], "ADD E", 1),
    0x84 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)+((state.cpu.reg.H)&0xF) > 0xF) else 0),
                 set_flags("SZ5H3V0C", value=lambda state : state.cpu.reg.A + state.cpu.reg.H, key="value"),
                 LDr('A') ],        [], "ADD H", 1),
    0x85 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)+((state.cpu.reg.L)&0xF) > 0xF) else 0),
                 set_flags("SZ5H3V0C", value=lambda state : state.cpu.reg.A + state.cpu.reg.L, key="value"),
                 LDr('A') ],        [], "ADD L", 1),
    0x86 : (0, [],                  [ MR(indirect="HL",
                                        action=do_each(
                                            force_flag('H', lambda  state,v : 1 if (((state.cpu.reg.A)&0xF)+(v&0xF) > 0xF) else 0),
                                            set_flags("SZ5H3V0C",
                                                        value=lambda state, v : state.cpu.reg.A + v,
                                                        dest="A"))) ], "ADD (HL)", 1),
    0x87 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)+((state.cpu.reg.A)&0xF) > 0xF) else 0),
                 set_flags("SZ5H3V0C", value=lambda state : state.cpu.reg.A + state.cpu.reg.A, key="value"),
                 LDr('A') ],        [], "ADD A", 1),
    0x88 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)+((state.cpu.reg.B)&0xF)+state.cpu.reg.getflag('C') > 0xF) else 0),
                 set_flags("SZ5H3V0C", value=lambda state : state.cpu.reg.A + state.cpu.reg.B + state.cpu.reg.getflag('C'), key="value"),
                 LDr('A') ],        [], "ADC B", 1),
    0x89 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)+((state.cpu.reg.C)&0xF)+state.cpu.reg.getflag('C') > 0xF) else 0),
                 set_flags("SZ5H3V0C", value=lambda state : state.cpu.reg.A + state.cpu.reg.C + state.cpu.reg.getflag('C'), key="value"),
                 LDr('A') ],        [], "ADC C", 1),
    0x8A : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)+((state.cpu.reg.D)&0xF)+state.cpu.reg.getflag('C') > 0xF) else 0),
                 set_flags("SZ5H3V0C", value=lambda state : state.cpu.reg.A + state.cpu.reg.D + state.cpu.reg.getflag('C'), key="value"),
                 LDr('A') ],        [], "ADC D", 1),
    0x8B : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)+((state.cpu.reg.E)&0xF)+state.cpu.reg.getflag('C') > 0xF) else 0),
                 set_flags("SZ5H3V0C", value=lambda state : state.cpu.reg.A + state.cpu.reg.E + state.cpu.reg.getflag('C'), key="value"),
                 LDr('A') ],        [], "ADC E", 1),
    0x8C : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)+((state.cpu.reg.H)&0xF)+state.cpu.reg.getflag('C') > 0xF) else 0),
                 set_flags("SZ5H3V0C", value=lambda state : state.cpu.reg.A + state.cpu.reg.H + state.cpu.reg.getflag('C'), key="value"),
                 LDr('A') ],        [], "ADC H", 1),
    0x8D : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)+((state.cpu.reg.L)&0xF)+state.cpu.reg.getflag('C') > 0xF) else 0),
                 set_flags("SZ5H3V0C", value=lambda state : state.cpu.reg.A + state.cpu.reg.L + state.cpu.reg.getflag('C'), key="value"),
                 LDr('A') ],        [], "ADC L", 1),
    0x8E : (0, [],                  [ MR(indirect="HL",
                                        action=do_each(
                                            force_flag('H', lambda  state,v : 1 if (((state.cpu.reg.A)&0xF)+(v&0xF)+state.cpu.reg.getflag('C') > 0xF) else 0),
                                            set_flags("SZ5H3V0C",
                                                        value=lambda state, v : state.cpu.reg.A + v + state.cpu.reg.getflag('C'),
                                                        dest="A"))) ], "ADC (HL)", 1),
    0x8F : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)+((state.cpu.reg.A)&0xF)+state.cpu.reg.getflag('C') > 0xF) else 0),
                 set_flags("SZ5H3V0C", value=lambda state : state.cpu.reg.A + state.cpu.reg.A + state.cpu.reg.getflag('C'), key="value"),
                 LDr('A') ],        [], "ADC A", 1),
    0x90 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)-((state.cpu.reg.B)&0xF) < 0x0) else 0),
                 set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.B, key="value"),
                 LDr('A') ],        [], "SUB B", 1),
    0x91 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)-((state.cpu.reg.C)&0xF) < 0x0) else 0),
                 set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.C, key="value"),
                 LDr('A') ],        [], "SUB C", 1),
    0x92 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)-((state.cpu.reg.D)&0xF) < 0x0) else 0),
                 set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.D, key="value"),
                 LDr('A') ],        [], "SUB D", 1),
    0x93 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)-((state.cpu.reg.E)&0xF) < 0x0) else 0),
                 set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.E, key="value"),
                 LDr('A') ],        [], "SUB E", 1),
    0x94 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)-((state.cpu.reg.H)&0xF) < 0x0) else 0),
                 set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.H, key="value"),
                 LDr('A') ],        [], "SUB H", 1),
    0x95 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)-((state.cpu.reg.L)&0xF) < 0x0) else 0),
                 set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.L, key="value"),
                 LDr('A') ],        [], "SUB L", 1),
    0x96 : (0, [],                  [ MR(indirect="HL",
                                        action=do_each(
                                            force_flag('H', lambda  state,v : 1 if (((state.cpu.reg.A)&0xF)-(v&0xF) < 0x0) else 0),
                                            set_flags("SZ5H3V1C",
                                                        value=lambda state, v : state.cpu.reg.A - v,
                                                        dest="A"))) ], "SUB (HL)"),
    0x97 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)-((state.cpu.reg.A)&0xF) < 0x0) else 0),
                 set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.A, key="value"),
                 LDr('A') ],        [], "SUB A", 1),
    0x98 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)-((state.cpu.reg.B)&0xF) - state.cpu.reg.getflag('C') < 0x0) else 0),
                 set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.B - state.cpu.reg.getflag('C'), key="value"),
                 LDr('A') ],        [], "SBC B", 1),
    0x99 : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)-((state.cpu.reg.C)&0xF) - state.cpu.reg.getflag('C') < 0x0) else 0),
                 set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.C - state.cpu.reg.getflag('C'), key="value"),
                 LDr('A') ],        [], "SBC C", 1),
    0x9A : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)-((state.cpu.reg.D)&0xF) - state.cpu.reg.getflag('C') < 0x0) else 0),
                 set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.D - state.cpu.reg.getflag('C'), key="value"),
                 LDr('A') ],        [], "SBC D", 1),
    0x9B : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)-((state.cpu.reg.E)&0xF) - state.cpu.reg.getflag('C') < 0x0) else 0),
                 set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.E - state.cpu.reg.getflag('C'), key="value"),
                 LDr('A') ],        [], "SBC E", 1),
    0x9C : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)-((state.cpu.reg.H)&0xF) - state.cpu.reg.getflag('C') < 0x0) else 0),
                 set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.H - state.cpu.reg.getflag('C'), key="value"),
                 LDr('A') ],        [], "SBC H", 1),
    0x9D : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)-((state.cpu.reg.L)&0xF) - state.cpu.reg.getflag('C') < 0x0) else 0),
                 set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.L - state.cpu.reg.getflag('C'), key="value"),
                 LDr('A') ],        [], "SBC L", 1),
    0x9E : (0, [],                  [ MR(indirect="HL",
                                        action=do_each(
                                            force_flag('H', lambda  state,v : 1 if (((state.cpu.reg.A)&0xF)-(v&0xF) - state.cpu.reg.getflag('C') < 0x0) else 0),
                                            set_flags("SZ5H3V1C",
                                                        value=lambda state, v : state.cpu.reg.A - v - state.cpu.reg.getflag('C'),
                                                        dest="A"))) ], "SBC (HL)", 1),
    0x9F : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.A)&0xF)-((state.cpu.reg.A)&0xF) - state.cpu.reg.getflag('C') < 0x0) else 0),
                 set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.A - state.cpu.reg.getflag('C'), key="value"),
                 LDr('A') ],        [], "SBC A", 1),
    0xA0 : (0, [ set_flags("SZ513P00", value=lambda state : state.cpu.reg.A & state.cpu.reg.B, key="value"),
                 LDr('A') ],        [], "AND B", 1),
    0xA1 : (0, [ set_flags("SZ513P00", value=lambda state : state.cpu.reg.A & state.cpu.reg.C, key="value"),
                 LDr('A') ],        [], "AND C", 1),
    0xA2 : (0, [ set_flags("SZ513P00", value=lambda state : state.cpu.reg.A & state.cpu.reg.D, key="value"),
                 LDr('A') ],        [], "AND D", 1),
    0xA3 : (0, [ set_flags("SZ513P00", value=lambda state : state.cpu.reg.A & state.cpu.reg.E, key="value"),
                 LDr('A') ],        [], "AND E", 1),
    0xA4 : (0, [ set_flags("SZ513P00", value=lambda state : state.cpu.reg.A & state.cpu.reg.H, key="value"),
                 LDr('A') ],        [], "AND H", 1),
    0xA5 : (0, [ set_flags("SZ513P00", value=lambda state : state.cpu.reg.A & state.cpu.reg.L, key="value"),
                 LDr('A') ],        [], "AND L", 1),
    0xA6 : (0, [],                  [ MR(indirect="HL",
                                        action=set_flags("SZ513P00",
                                                        value=lambda state, v : state.cpu.reg.A & v,
                                                        dest="A")) ], "AND (HL)", 1),
    0xA7 : (0, [ set_flags("SZ513P00", value=lambda state : state.cpu.reg.A & state.cpu.reg.A, key="value"),
                 LDr('A') ],        [], "AND A", 1),
    0xA8 : (0, [ set_flags("SZ503P00", value=lambda state : state.cpu.reg.A ^ state.cpu.reg.B, key="value"),
                 LDr('A') ],        [], "XOR B", 1),
    0xA9 : (0, [ set_flags("SZ503P00", value=lambda state : state.cpu.reg.A ^ state.cpu.reg.C, key="value"),
                 LDr('A') ],        [], "XOR C", 1),
    0xAA : (0, [ set_flags("SZ503P00", value=lambda state : state.cpu.reg.A ^ state.cpu.reg.D, key="value"),
                 LDr('A') ],        [], "XOR D", 1),
    0xAB : (0, [ set_flags("SZ503P00", value=lambda state : state.cpu.reg.A ^ state.cpu.reg.E, key="value"),
                 LDr('A') ],        [], "XOR E", 1),
    0xAC : (0, [ set_flags("SZ503P00", value=lambda state : state.cpu.reg.A ^ state.cpu.reg.H, key="value"),
                 LDr('A') ],        [], "XOR H", 1),
    0xAD : (0, [ set_flags("SZ503P00", value=lambda state : state.cpu.reg.A ^ state.cpu.reg.L, key="value"),
                 LDr('A') ],        [], "XOR L", 1),
    0xAE : (0, [],                  [ MR(indirect="HL",
                                        action=set_flags("SZ503P00",
                                                        value=lambda state, v : state.cpu.reg.A ^ v,
                                                        dest="A")) ], "XOR (HL)", 1),
    0xAF : (0, [ set_flags("SZ503P00", value=lambda state : state.cpu.reg.A ^ state.cpu.reg.A, key="value"),
                 LDr('A') ],        [], "XOR A", 1),
    0xB0 : (0, [ set_flags("SZ503P00", value=lambda state : state.cpu.reg.A | state.cpu.reg.B, key="value"),
                 LDr('A') ],        [], "OR B", 1),
    0xB1 : (0, [ set_flags("SZ503P00", value=lambda state : state.cpu.reg.A | state.cpu.reg.C, key="value"),
                 LDr('A') ],        [], "OR C", 1),
    0xB2 : (0, [ set_flags("SZ503P00", value=lambda state : state.cpu.reg.A | state.cpu.reg.D, key="value"),
                 LDr('A') ],        [], "OR D", 1),
    0xB3 : (0, [ set_flags("SZ503P00", value=lambda state : state.cpu.reg.A | state.cpu.reg.E, key="value"),
                 LDr('A') ],        [], "OR E", 1),
    0xB4 : (0, [ set_flags("SZ503P00", value=lambda state : state.cpu.reg.A | state.cpu.reg.H, key="value"),
                 LDr('A') ],        [], "OR H", 1),
    0xB5 : (0, [ set_flags("SZ503P00", value=lambda state : state.cpu.reg.A | state.cpu.reg.L, key="value"),
                 LDr('A') ],        [], "OR L", 1),
    0xB6 : (0, [],                  [ MR(indirect="HL",
                                        action=set_flags("SZ503P00",
                                                        value=lambda state, v : state.cpu.reg.A | v,
                                                        dest="A")) ], "OR (HL)", 1),
    0xB7 : (0, [ set_flags("SZ503P00", value=lambda state : state.cpu.reg.A | state.cpu.reg.A, key="value"),
                 LDr('A') ],        [], "OR A", 1),
    0xB8 : (0, [ set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.B, key="value") ],
                                    [], "CP B", 1),
    0xB9 : (0, [ set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.C, key="value"), ],
                                    [], "CP C", 1),
    0xBA : (0, [ set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.D, key="value"), ],
                                    [], "CP D", 1),
    0xBB : (0, [ set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.E, key="value"), ],
                                    [], "CP E", 1),
    0xBC : (0, [ set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.H, key="value"), ],
                                    [], "CP H", 1),
    0xBD : (0, [ set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.L, key="value"), ],
                                    [], "CP L", 1),
    0xBE : (0, [],                  [ MR(indirect="HL",
                                        action=set_flags("SZ5H3V1C",
                                                        value=lambda state, v : state.cpu.reg.A - v,)
                                                                 ) ], "CP (HL)", 1),
    0xBF : (0, [ set_flags("SZ5H3V1C", value=lambda state : state.cpu.reg.A - state.cpu.reg.A, key="value"), ],
                                    [], "CP A", 1),
    0xC0 : (1, [ on_flag('Z', early_abort()) ],
                                    [ SR(), SR(action=JP()) ], "RET NZ", 1),
    0xC1 : (0, [],                  [ SR(), SR(action=LDr("BC")) ], "POP BC", 1),
    0xC2 : (0, [],                  [ OD(), OD(action=unless_flag("Z",JP())) ], "JP NZ,nn", 3),
    0xC3 : (0, [],                  [ OD(), OD(action=JP()) ], "JP nn", 3),
    0xC4 : (0, [],                  [ OD(), OD(action=do_each(RRr("target"),
                                                              on_flag("Z", early_abort()))),
                                      SW(source="PCH"), SW(source="PCL", action=JP(key="target")) ], "CALL NZ,nn", 3),
    0xC5 : (1, [],                  [ SW(source="B"), SW(source="C") ], "PUSH BC", 1),
    0xC6 : (0, [],                  [ OD(action=do_each(
                                                force_flag('H', lambda  state,v : 1 if (((state.cpu.reg.A)&0xF)+(v&0xF) > 0xF) else 0),
                                                set_flags("SZ5H3V0C",
                                                        value=lambda state, v : state.cpu.reg.A + v,
                                                        dest="A"))) ], "ADD n", 2),
    0xC7 : (1, [],                  [ SW(source="PCH"), SW(source="PCL", action=JP(0x0000)) ], "RST 00H", 1),
    0xC8 : (1, [ unless_flag('Z', early_abort()) ],
                                    [ SR(), SR(action=JP()) ], "RET NZ", 1),
    0xC9 : (0, [],                  [ SR(), SR(action=JP()) ], "RET", 1),
    0xCA : (0, [],                  [ OD(), OD(action=on_flag("Z",JP())) ], "JP Z,nn", 3),
    0xCB : (0, [],                  [ OCF(prefix=0xCB) ], "", 0),
    0xCC : (0, [],                  [ OD(), OD(action=do_each(RRr("target"),
                                                              unless_flag("Z", early_abort()))),
                                      SW(source="PCH"), SW(source="PCL", action=JP(key="target")) ], "CALL Z,nn", 3),
    0xCD : (0, [],                  [ OD(), OD(action=RRr("target")),
                                      SW(source="PCH"), SW(source="PCL", action=JP(key="target")) ], "CALL nn", 3),
    0xCE : (0, [],                  [ OD(action=do_each(force_flag('H', lambda  state,v : 1 if (((state.cpu.reg.A)&0xF)+(v&0xF)+state.cpu.reg.getflag('C') > 0xF) else 0),
                                                        set_flags("SZ5H3V0C",
                                                        value=lambda state, v : state.cpu.reg.A + v + state.cpu.reg.getflag('C'),
                                                        dest="A"))) ], "ADC n", 2),
    0xCF : (1, [],                  [ SW(source="PCH"), SW(source="PCL", action=JP(0x0008)) ], "RST 08H", 1),
    0xD0 : (1, [ on_flag('C', early_abort()) ],
                                    [ SR(), SR(action=JP()) ], "RET NC", 1),
    0xD1 : (0, [],                  [ SR(), SR(action=LDr("DE")) ], "POP DE", 1),
    0xD2 : (0, [],                  [ OD(), OD(action=unless_flag("C",JP())) ], "JP NC,nn", 3),
    0xD3 : (0, [],                  [ OD(key="address"), PW(high="A", source="A") ], "OUT (n),A", 2),
    0xD4 : (0, [],                  [ OD(), OD(action=do_each(RRr("target"),
                                                              on_flag("C", early_abort()))),
                                      SW(source="PCH"), SW(source="PCL", action=JP(key="target")) ], "CALL NC,nn", 3),
    0xD5 : (1, [],                  [ SW(source="D"), SW(source="E") ], "PUSH DE", 1),
    0xD6 : (0, [],                  [ OD(action=do_each(
                                                force_flag('H', lambda  state,v : 1 if (((state.cpu.reg.A)&0xF)-(v&0xF) < 0x0) else 0),
                                                set_flags("SZ5H3V1C",
                                                        value=lambda state, v : state.cpu.reg.A - v,
                                                        dest="A"))) ], "SUB n", 2),
    0xD7 : (1, [],                  [ SW(source="PCH"), SW(source="PCL", action=JP(0x0010)) ], "RST 10H", 1),
    0xD8 : (1, [ unless_flag('C', early_abort()) ],
                                    [ SR(), SR(action=JP()) ], "RET C", 1),
    0xDA : (0, [],                  [ OD(), OD(action=on_flag("C",JP())) ], "JP C,nn", 3),
    0xDB : (0, [],                  [ OD(), PR(high="A", dest="A") ], "IN A,n", 2),
    0xDC : (0, [],                  [ OD(), OD(action=do_each(RRr("target"),
                                                              unless_flag("C", early_abort()))),
                                      SW(source="PCH"), SW(source="PCL", action=JP(key="target")) ], "CALL C,nn", 3),
    0xDE : (0, [],                  [ OD(action=do_each(
                                            force_flag('H', lambda  state,v : 1 if (((state.cpu.reg.A)&0xF)-(v&0xF) - state.cpu.reg.getflag('C') < 0x0) else 0),
                                            set_flags("SZ5H3V1C",
                                                        value=lambda state, v : state.cpu.reg.A - v - state.cpu.reg.getflag('C'),
                                                        dest="A"))) ], "SBC n", 2),
    0xD9 : (0, [ EXX() ],           [], "EXX", 1),
    0xDD : (0, [],                  [ OCF(prefix=0xDD) ], "", 0),
    0xDF : (1, [],                  [ SW(source="PCH"), SW(source="PCL", action=JP(0x0018)) ], "RST 18H", 1),
    0xE0 : (1, [ on_flag('P', early_abort()) ],
                                    [ SR(), SR(action=JP()) ], "RET PO", 1),
    0xE1 : (0, [],                  [ SR(), SR(action=LDr("HL")) ], "POP HL", 1),
    0xE2 : (0, [],                  [ OD(), OD(action=unless_flag("P",JP())) ], "JP PO,nn", 3),
    0xE3 : (0, [ RRr('H','H'), RRr('L','L') ],  [ SR(), SR(action=LDr("HL"), extra=1),
                                                      SW(key="H"), SW(key="L", extra=2) ], "EX (SP),HL", 1),
    0xE4 : (0, [],                  [ OD(), OD(action=do_each(RRr("target"),
                                                              on_flag("P", early_abort()))),
                                      SW(source="PCH"), SW(source="PCL", action=JP(key="target")) ], "CALL PO,nn", 3),
    0xE5 : (1, [],                  [ SW(source="H"), SW(source="L") ], "PUSH HL", 1),
    0xE6 : (0, [],                  [ OD(action=set_flags("SZ513P00",
                                                        value=lambda state, v : state.cpu.reg.A & v,
                                                        dest="A")) ], "AND n", 2),
    0xE7 : (1, [],                  [ SW(source="PCH"), SW(source="PCL", action=JP(0x0020)) ], "RST 20H", 1),
    0xE8 : (1, [ unless_flag('P', early_abort()) ],
                                    [ SR(), SR(action=JP()) ], "RET PE", 1),
    0xE9 : (0, [ JP(source="HL") ], [], "JP (HL)", 1),
    0xEA : (0, [],                  [ OD(), OD(action=on_flag("P",JP())) ], "JP PE,nn", 3),
    0xEB : (0, [ EX('DE', 'HL') ],  [], "EX DE,HL", 1),
    0xEC : (0, [],                  [ OD(), OD(action=do_each(RRr("target"),
                                                              unless_flag("P", early_abort()))),
                                      SW(source="PCH"), SW(source="PCL", action=JP(key="target")) ], "CALL PE,nn", 3),
    0xED : (0, [],                  [ OCF(prefix=0xED) ], "", 0),
    0xEE : (0, [],                  [ OD(action=set_flags("SZ503P00",
                                                        value=lambda state, v : state.cpu.reg.A ^ v,
                                                        dest="A")) ], "XOR n", 2),
    0xEF : (1, [],                  [ SW(source="PCH"), SW(source="PCL", action=JP(0x0028)) ], "RST 28H", 1),
    0xF0 : (1, [ on_flag('S', early_abort()) ],
                                    [ SR(), SR(action=JP()) ], "RET P", 1),
    0xF1 : (0, [],                  [ SR(), SR(action=LDr("AF")) ], "POP AF", 1),
    0xF2 : (0, [],                  [ OD(), OD(action=unless_flag("S",JP())) ], "JP P,nn", 3),
    0xF3 : (0, [ di() ],            [], "DI", 1),
    0xF4 : (0, [],                  [ OD(), OD(action=do_each(RRr("target"),
                                                              on_flag("S", early_abort()))),
                                      SW(source="PCH"), SW(source="PCL", action=JP(key="target")) ], "CALL P,nn", 3),
    0xF5 : (1, [],                  [ SW(source="A"), SW(source="F") ], "PUSH AF", 1),
    0xF6 : (0, [],                  [ OD(action=set_flags("SZ503P00",
                                                        value=lambda state, v : state.cpu.reg.A | v,
                                                        dest="A")) ], "OR n", 2),
    0xF7 : (1, [],                  [ SW(source="PCH"), SW(source="PCL", action=JP(0x0030)) ], "RST 30H", 1),
    0xF8 : (1, [ unless_flag('S', early_abort()) ],
                                    [ SR(), SR(action=JP()) ], "RET M", 1),
    0xF9 : (0, [ LDrs('SP', 'HL') ], [], "LD SP,HL", 1),
    0xFA : (0, [],                  [ OD(), OD(action=on_flag("S",JP())) ], "JP M,nn", 3),
    0xFB : (0, [ ei() ],            [], "EI", 1),
    0xFC : (0, [],                  [ OD(), OD(action=do_each(RRr("target"),
                                                              unless_flag("S", early_abort()))),
                                      SW(source="PCH"), SW(source="PCL", action=JP(key="target")) ], "CALL M,nn", 3),
    0xFD : (0, [],                  [ OCF(prefix=0xFD) ], "", 0),
    0xFE : (0, [],                  [ OD(action=set_flags("SZ5H3V1C",
                                                        value=lambda state, v : state.cpu.reg.A - v,
                                                        )) ], "CP n", 2),
    0xFF : (1, [],                  [ SW(source="PCH"), SW(source="PCL", action=JP(0x0038)) ], "RST 38H", 1),

    # Multibyte opcodes
    (0xCB, 0x00) : (0, [ RLC("B") ],            [], "RLC B", 2),
    (0xCB, 0x01) : (0, [ RLC("C") ],            [], "RLC C", 2),
    (0xCB, 0x02) : (0, [ RLC("D") ],            [], "RLC D", 2),
    (0xCB, 0x03) : (0, [ RLC("E") ],            [], "RLC E", 2),
    (0xCB, 0x04) : (0, [ RLC("H") ],            [], "RLC H", 2),
    (0xCB, 0x05) : (0, [ RLC("L") ],            [], "RLC L", 2),
    (0xCB, 0x06) : (0, [],                      [ MR(indirect="HL", action=RLC()), MW(indirect="HL") ], "RLC (HL)", 2),
    (0xCB, 0x07) : (0, [ RLC("A") ],            [], "RLC A", 2),
    (0xCB, 0x08) : (0, [ RRC("B") ],            [], "RRC B", 2),
    (0xCB, 0x09) : (0, [ RRC("C") ],            [], "RRC C", 2),
    (0xCB, 0x0A) : (0, [ RRC("D") ],            [], "RRC D", 2),
    (0xCB, 0x0B) : (0, [ RRC("E") ],            [], "RRC E", 2),
    (0xCB, 0x0C) : (0, [ RRC("H") ],            [], "RRC H", 2),
    (0xCB, 0x0D) : (0, [ RRC("L") ],            [], "RRC L", 2),
    (0xCB, 0x0E) : (0, [],                      [ MR(indirect="HL", action=RRC()), MW(indirect="HL") ], "RRC (HL)", 2),
    (0xCB, 0x0F) : (0, [ RRC("A") ],            [], "RRC A", 2),
    (0xCB, 0x10) : (0, [ RL("B") ],             [], "RL B", 2),
    (0xCB, 0x11) : (0, [ RL("C") ],             [], "RL C", 2),
    (0xCB, 0x12) : (0, [ RL("D") ],             [], "RL D", 2),
    (0xCB, 0x13) : (0, [ RL("E") ],             [], "RL E", 2),
    (0xCB, 0x14) : (0, [ RL("H") ],             [], "RL H", 2),
    (0xCB, 0x15) : (0, [ RL("L") ],             [], "RL L", 2),
    (0xCB, 0x16) : (0, [],                      [ MR(indirect="HL", action=RL()), MW(indirect="HL") ], "RL (HL)", 2),
    (0xCB, 0x17) : (0, [ RL("A") ],             [], "RL A", 2),
    (0xCB, 0x18) : (0, [ RR("B") ],             [], "RR B", 2),
    (0xCB, 0x19) : (0, [ RR("C") ],             [], "RR C", 2),
    (0xCB, 0x1A) : (0, [ RR("D") ],             [], "RR D", 2),
    (0xCB, 0x1B) : (0, [ RR("E") ],             [], "RR E", 2),
    (0xCB, 0x1C) : (0, [ RR("H") ],             [], "RR H", 2),
    (0xCB, 0x1D) : (0, [ RR("L") ],             [], "RR L", 2),
    (0xCB, 0x1E) : (0, [],                      [ MR(indirect="HL", action=RR()), MW(indirect="HL") ], "RR (HL)", 2),
    (0xCB, 0x1F) : (0, [ RR("A") ],             [], "RR A", 2),
    (0xCB, 0x20) : (0, [ SLA("B") ],            [], "SLA B", 2),
    (0xCB, 0x21) : (0, [ SLA("C") ],            [], "SLA C", 2),
    (0xCB, 0x22) : (0, [ SLA("D") ],            [], "SLA D", 2),
    (0xCB, 0x23) : (0, [ SLA("E") ],            [], "SLA E", 2),
    (0xCB, 0x24) : (0, [ SLA("H") ],            [], "SLA H", 2),
    (0xCB, 0x25) : (0, [ SLA("L") ],            [], "SLA L", 2),
    (0xCB, 0x26) : (0, [],                      [ MR(indirect="HL", action=SLA()), MW(indirect="HL") ], "SLA (HL)", 2),
    (0xCB, 0x27) : (0, [ SLA("A") ],            [], "SLA A", 2),
    (0xCB, 0x28) : (0, [ SRA("B") ],            [], "SRA B", 2),
    (0xCB, 0x29) : (0, [ SRA("C") ],            [], "SRA C", 2),
    (0xCB, 0x2A) : (0, [ SRA("D") ],            [], "SRA D", 2),
    (0xCB, 0x2B) : (0, [ SRA("E") ],            [], "SRA E", 2),
    (0xCB, 0x2C) : (0, [ SRA("H") ],            [], "SRA H", 2),
    (0xCB, 0x2D) : (0, [ SRA("L") ],            [], "SRA L", 2),
    (0xCB, 0x2E) : (0, [],                      [ MR(indirect="HL", action=SRA()), MW(indirect="HL") ], "SRA (HL)", 2),
    (0xCB, 0x2F) : (0, [ SRA("A") ],            [], "SRA A", 2),
    (0xCB, 0x30) : (0, [ SL1("B") ],            [], "SL1 B (undocumemnted)", 2),
    (0xCB, 0x31) : (0, [ SL1("C") ],            [], "SL1 C (undocumemnted)", 2),
    (0xCB, 0x32) : (0, [ SL1("D") ],            [], "SL1 D (undocumemnted)", 2),
    (0xCB, 0x33) : (0, [ SL1("E") ],            [], "SL1 E (undocumemnted)", 2),
    (0xCB, 0x34) : (0, [ SL1("H") ],            [], "SL1 H (undocumemnted)", 2),
    (0xCB, 0x35) : (0, [ SL1("L") ],            [], "SL1 L (undocumemnted)", 2),
    (0xCB, 0x36) : (0, [],                      [ MR(indirect="HL", action=SL1()), MW(indirect="HL") ], "SL1 (HL) (undocumemnted)", 2),
    (0xCB, 0x37) : (0, [ SL1("A") ],            [], "SL1 A (undocumemnted)", 2),
    (0xCB, 0x38) : (0, [ SRL("B") ],            [], "SRL B", 2),
    (0xCB, 0x39) : (0, [ SRL("C") ],            [], "SRL C", 2),
    (0xCB, 0x3A) : (0, [ SRL("D") ],            [], "SRL D", 2),
    (0xCB, 0x3B) : (0, [ SRL("E") ],            [], "SRL E", 2),
    (0xCB, 0x3C) : (0, [ SRL("H") ],            [], "SRL H", 2),
    (0xCB, 0x3D) : (0, [ SRL("L") ],            [], "SRL L", 2),
    (0xCB, 0x3E) : (0, [],                      [ MR(indirect="HL", action=SRL()), MW(indirect="HL") ], "SRL (HL)", 2),
    (0xCB, 0x3F) : (0, [ SRL("A") ],            [], "SRL A", 2),
    (0xCB, 0x40) : (0, [ BIT(0, "B") ],         [], "BIT 0,B", 2),
    (0xCB, 0x41) : (0, [ BIT(0, "C") ],         [], "BIT 0,C", 2),
    (0xCB, 0x42) : (0, [ BIT(0, "D") ],         [], "BIT 0,D", 2),
    (0xCB, 0x43) : (0, [ BIT(0, "E") ],         [], "BIT 0,E", 2),
    (0xCB, 0x44) : (0, [ BIT(0, "H") ],         [], "BIT 0,H", 2),
    (0xCB, 0x45) : (0, [ BIT(0, "L") ],         [], "BIT 0,L", 2),
    (0xCB, 0x46) : (0, [],                      [ MR(indirect="HL", action=BIT(0)) ], "BIT 0,(HL)", 2),
    (0xCB, 0x47) : (0, [ BIT(0, "A") ],         [], "BIT 0,A", 2),
    (0xCB, 0x48) : (0, [ BIT(1, "B") ],         [], "BIT 1,B", 2),
    (0xCB, 0x49) : (0, [ BIT(1, "C") ],         [], "BIT 1,C", 2),
    (0xCB, 0x4A) : (0, [ BIT(1, "D") ],         [], "BIT 1,D", 2),
    (0xCB, 0x4B) : (0, [ BIT(1, "E") ],         [], "BIT 1,E", 2),
    (0xCB, 0x4C) : (0, [ BIT(1, "H") ],         [], "BIT 1,H", 2),
    (0xCB, 0x4D) : (0, [ BIT(1, "L") ],         [], "BIT 1,L", 2),
    (0xCB, 0x4E) : (0, [],                      [ MR(indirect="HL", action=BIT(1)) ], "BIT 1,(HL)", 2),
    (0xCB, 0x4F) : (0, [ BIT(1, "A") ],         [], "BIT 1,A", 2),
    (0xCB, 0x50) : (0, [ BIT(2, "B") ],         [], "BIT 2,B", 2),
    (0xCB, 0x51) : (0, [ BIT(2, "C") ],         [], "BIT 2,C", 2),
    (0xCB, 0x52) : (0, [ BIT(2, "D") ],         [], "BIT 2,D", 2),
    (0xCB, 0x53) : (0, [ BIT(2, "E") ],         [], "BIT 2,E", 2),
    (0xCB, 0x54) : (0, [ BIT(2, "H") ],         [], "BIT 2,H", 2),
    (0xCB, 0x55) : (0, [ BIT(2, "L") ],         [], "BIT 2,L", 2),
    (0xCB, 0x56) : (0, [],                      [ MR(indirect="HL", action=BIT(2)) ], "BIT 2,(HL)", 2),
    (0xCB, 0x57) : (0, [ BIT(2, "A") ],         [], "BIT 2,A", 2),
    (0xCB, 0x58) : (0, [ BIT(3, "B") ],         [], "BIT 3,B", 2),
    (0xCB, 0x59) : (0, [ BIT(3, "C") ],         [], "BIT 3,C", 2),
    (0xCB, 0x5A) : (0, [ BIT(3, "D") ],         [], "BIT 3,D", 2),
    (0xCB, 0x5B) : (0, [ BIT(3, "E") ],         [], "BIT 3,E", 2),
    (0xCB, 0x5C) : (0, [ BIT(3, "H") ],         [], "BIT 3,H", 2),
    (0xCB, 0x5D) : (0, [ BIT(3, "L") ],         [], "BIT 3,L", 2),
    (0xCB, 0x5E) : (0, [],                      [ MR(indirect="HL", action=BIT(3)) ], "BIT 3,(HL)", 2),
    (0xCB, 0x5F) : (0, [ BIT(3, "A") ],         [], "BIT 3,A", 2),
    (0xCB, 0x60) : (0, [ BIT(4, "B") ],         [], "BIT 4,B", 2),
    (0xCB, 0x61) : (0, [ BIT(4, "C") ],         [], "BIT 4,C", 2),
    (0xCB, 0x62) : (0, [ BIT(4, "D") ],         [], "BIT 4,D", 2),
    (0xCB, 0x63) : (0, [ BIT(4, "E") ],         [], "BIT 4,E", 2),
    (0xCB, 0x64) : (0, [ BIT(4, "H") ],         [], "BIT 4,H", 2),
    (0xCB, 0x65) : (0, [ BIT(4, "L") ],         [], "BIT 4,L", 2),
    (0xCB, 0x66) : (0, [],                      [ MR(indirect="HL", action=BIT(4)) ], "BIT 4,(HL)", 2),
    (0xCB, 0x67) : (0, [ BIT(4, "A") ],         [], "BIT 4,A", 2),
    (0xCB, 0x68) : (0, [ BIT(5, "B") ],         [], "BIT 5,B", 2),
    (0xCB, 0x69) : (0, [ BIT(5, "C") ],         [], "BIT 5,C", 2),
    (0xCB, 0x6A) : (0, [ BIT(5, "D") ],         [], "BIT 5,D", 2),
    (0xCB, 0x6B) : (0, [ BIT(5, "E") ],         [], "BIT 5,E", 2),
    (0xCB, 0x6C) : (0, [ BIT(5, "H") ],         [], "BIT 5,H", 2),
    (0xCB, 0x6D) : (0, [ BIT(5, "L") ],         [], "BIT 5,L", 2),
    (0xCB, 0x6E) : (0, [],                      [ MR(indirect="HL", action=BIT(5)) ], "BIT 5,(HL)", 2),
    (0xCB, 0x6F) : (0, [ BIT(5, "A") ],         [], "BIT 5,A", 2),
    (0xCB, 0x70) : (0, [ BIT(6, "B") ],         [], "BIT 6,B", 2),
    (0xCB, 0x71) : (0, [ BIT(6, "C") ],         [], "BIT 6,C", 2),
    (0xCB, 0x72) : (0, [ BIT(6, "D") ],         [], "BIT 6,D", 2),
    (0xCB, 0x73) : (0, [ BIT(6, "E") ],         [], "BIT 6,E", 2),
    (0xCB, 0x74) : (0, [ BIT(6, "H") ],         [], "BIT 6,H", 2),
    (0xCB, 0x75) : (0, [ BIT(6, "L") ],         [], "BIT 6,L", 2),
    (0xCB, 0x76) : (0, [],                      [ MR(indirect="HL", action=BIT(6)) ], "BIT 6,(HL)", 2),
    (0xCB, 0x77) : (0, [ BIT(6, "A") ],         [], "BIT 6,A", 2),
    (0xCB, 0x78) : (0, [ BIT(7, "B") ],         [], "BIT 7,B", 2),
    (0xCB, 0x79) : (0, [ BIT(7, "C") ],         [], "BIT 7,C", 2),
    (0xCB, 0x7A) : (0, [ BIT(7, "D") ],         [], "BIT 7,D", 2),
    (0xCB, 0x7B) : (0, [ BIT(7, "E") ],         [], "BIT 7,E", 2),
    (0xCB, 0x7C) : (0, [ BIT(7, "H") ],         [], "BIT 7,H", 2),
    (0xCB, 0x7D) : (0, [ BIT(7, "L") ],         [], "BIT 7,L", 2),
    (0xCB, 0x7E) : (0, [],                      [ MR(indirect="HL", action=BIT(7)) ], "BIT 7,(HL)", 2),
    (0xCB, 0x7F) : (0, [ BIT(7, "A") ],         [], "BIT 7,A", 2),
    (0xCB, 0x80) : (0, [ RES(0, "B") ],         [], "RES 0,B", 2),
    (0xCB, 0x81) : (0, [ RES(0, "C") ],         [], "RES 0,C", 2),
    (0xCB, 0x82) : (0, [ RES(0, "D") ],         [], "RES 0,D", 2),
    (0xCB, 0x83) : (0, [ RES(0, "E") ],         [], "RES 0,E", 2),
    (0xCB, 0x84) : (0, [ RES(0, "H") ],         [], "RES 0,H", 2),
    (0xCB, 0x85) : (0, [ RES(0, "L") ],         [], "RES 0,L", 2),
    (0xCB, 0x86) : (0, [],                      [ MR(indirect="HL", action=RES(0)), MW(indirect="HL") ], "RES 0,(HL)", 2),
    (0xCB, 0x87) : (0, [ RES(0, "A") ],         [], "RES 0,A", 2),
    (0xCB, 0x88) : (0, [ RES(1, "B") ],         [], "RES 1,B", 2),
    (0xCB, 0x89) : (0, [ RES(1, "C") ],         [], "RES 1,C", 2),
    (0xCB, 0x8A) : (0, [ RES(1, "D") ],         [], "RES 1,D", 2),
    (0xCB, 0x8B) : (0, [ RES(1, "E") ],         [], "RES 1,E", 2),
    (0xCB, 0x8C) : (0, [ RES(1, "H") ],         [], "RES 1,H", 2),
    (0xCB, 0x8D) : (0, [ RES(1, "L") ],         [], "RES 1,L", 2),
    (0xCB, 0x8E) : (0, [],                      [ MR(indirect="HL", action=RES(1)), MW(indirect="HL") ], "RES 1,(HL)", 2),
    (0xCB, 0x8F) : (0, [ RES(1, "A") ],         [], "RES 1,A", 2),
    (0xCB, 0x90) : (0, [ RES(2, "B") ],         [], "RES 2,B", 2),
    (0xCB, 0x91) : (0, [ RES(2, "C") ],         [], "RES 2,C", 2),
    (0xCB, 0x92) : (0, [ RES(2, "D") ],         [], "RES 2,D", 2),
    (0xCB, 0x93) : (0, [ RES(2, "E") ],         [], "RES 2,E", 2),
    (0xCB, 0x94) : (0, [ RES(2, "H") ],         [], "RES 2,H", 2),
    (0xCB, 0x95) : (0, [ RES(2, "L") ],         [], "RES 2,L", 2),
    (0xCB, 0x96) : (0, [],                      [ MR(indirect="HL", action=RES(2)), MW(indirect="HL") ], "RES 2,(HL)", 2),
    (0xCB, 0x97) : (0, [ RES(2, "A") ],         [], "RES 2,A", 2),
    (0xCB, 0x98) : (0, [ RES(3, "B") ],         [], "RES 3,B", 2),
    (0xCB, 0x99) : (0, [ RES(3, "C") ],         [], "RES 3,C", 2),
    (0xCB, 0x9A) : (0, [ RES(3, "D") ],         [], "RES 3,D", 2),
    (0xCB, 0x9B) : (0, [ RES(3, "E") ],         [], "RES 3,E", 2),
    (0xCB, 0x9C) : (0, [ RES(3, "H") ],         [], "RES 3,H", 2),
    (0xCB, 0x9D) : (0, [ RES(3, "L") ],         [], "RES 3,L", 2),
    (0xCB, 0x9E) : (0, [],                      [ MR(indirect="HL", action=RES(3)), MW(indirect="HL") ], "RES 3,(HL)", 2),
    (0xCB, 0x9F) : (0, [ RES(3, "A") ],         [], "RES 3,A", 2),
    (0xCB, 0xA0) : (0, [ RES(4, "B") ],         [], "RES 4,B", 2),
    (0xCB, 0xA1) : (0, [ RES(4, "C") ],         [], "RES 4,C", 2),
    (0xCB, 0xA2) : (0, [ RES(4, "D") ],         [], "RES 4,D", 2),
    (0xCB, 0xA3) : (0, [ RES(4, "E") ],         [], "RES 4,E", 2),
    (0xCB, 0xA4) : (0, [ RES(4, "H") ],         [], "RES 4,H", 2),
    (0xCB, 0xA5) : (0, [ RES(4, "L") ],         [], "RES 4,L", 2),
    (0xCB, 0xA6) : (0, [],                      [ MR(indirect="HL", action=RES(4)), MW(indirect="HL") ], "RES 4,(HL)", 2),
    (0xCB, 0xA7) : (0, [ RES(4, "A") ],         [], "RES 4,A", 2),
    (0xCB, 0xA8) : (0, [ RES(5, "B") ],         [], "RES 5,B", 2),
    (0xCB, 0xA9) : (0, [ RES(5, "C") ],         [], "RES 5,C", 2),
    (0xCB, 0xAA) : (0, [ RES(5, "D") ],         [], "RES 5,D", 2),
    (0xCB, 0xAB) : (0, [ RES(5, "E") ],         [], "RES 5,E", 2),
    (0xCB, 0xAC) : (0, [ RES(5, "H") ],         [], "RES 5,H", 2),
    (0xCB, 0xAD) : (0, [ RES(5, "L") ],         [], "RES 5,L", 2),
    (0xCB, 0xAE) : (0, [],                      [ MR(indirect="HL", action=RES(5)), MW(indirect="HL") ], "RES 5,(HL)", 2),
    (0xCB, 0xAF) : (0, [ RES(5, "A") ],         [], "RES 5,A", 2),
    (0xCB, 0xB0) : (0, [ RES(6, "B") ],         [], "RES 6,B", 2),
    (0xCB, 0xB1) : (0, [ RES(6, "C") ],         [], "RES 6,C", 2),
    (0xCB, 0xB2) : (0, [ RES(6, "D") ],         [], "RES 6,D", 2),
    (0xCB, 0xB3) : (0, [ RES(6, "E") ],         [], "RES 6,E", 2),
    (0xCB, 0xB4) : (0, [ RES(6, "H") ],         [], "RES 6,H", 2),
    (0xCB, 0xB5) : (0, [ RES(6, "L") ],         [], "RES 6,L", 2),
    (0xCB, 0xB6) : (0, [],                      [ MR(indirect="HL", action=RES(6)), MW(indirect="HL") ], "RES 6,(HL)", 2),
    (0xCB, 0xB7) : (0, [ RES(6, "A") ],         [], "RES 6,A", 2),
    (0xCB, 0xB8) : (0, [ RES(7, "B") ],         [], "RES 7,B", 2),
    (0xCB, 0xB9) : (0, [ RES(7, "C") ],         [], "RES 7,C", 2),
    (0xCB, 0xBA) : (0, [ RES(7, "D") ],         [], "RES 7,D", 2),
    (0xCB, 0xBB) : (0, [ RES(7, "E") ],         [], "RES 7,E", 2),
    (0xCB, 0xBC) : (0, [ RES(7, "H") ],         [], "RES 7,H", 2),
    (0xCB, 0xBD) : (0, [ RES(7, "L") ],         [], "RES 7,L", 2),
    (0xCB, 0xBE) : (0, [],                      [ MR(indirect="HL", action=RES(7)), MW(indirect="HL") ], "RES 7,(HL)", 2),
    (0xCB, 0xBF) : (0, [ RES(7, "A") ],         [], "RES 7,A", 2),
    (0xCB, 0xC0) : (0, [ SET(0, "B") ],         [], "SET 0,B", 2),
    (0xCB, 0xC1) : (0, [ SET(0, "C") ],         [], "SET 0,C", 2),
    (0xCB, 0xC2) : (0, [ SET(0, "D") ],         [], "SET 0,D", 2),
    (0xCB, 0xC3) : (0, [ SET(0, "E") ],         [], "SET 0,E", 2),
    (0xCB, 0xC4) : (0, [ SET(0, "H") ],         [], "SET 0,H", 2),
    (0xCB, 0xC5) : (0, [ SET(0, "L") ],         [], "SET 0,L", 2),
    (0xCB, 0xC6) : (0, [],                      [ MR(indirect="HL", action=SET(0)), MW(indirect="HL") ], "SET 0,(HL)", 2),
    (0xCB, 0xC7) : (0, [ SET(0, "A") ],         [], "SET 0,A", 2),
    (0xCB, 0xC8) : (0, [ SET(1, "B") ],         [], "SET 1,B", 2),
    (0xCB, 0xC9) : (0, [ SET(1, "C") ],         [], "SET 1,C", 2),
    (0xCB, 0xCA) : (0, [ SET(1, "D") ],         [], "SET 1,D", 2),
    (0xCB, 0xCB) : (0, [ SET(1, "E") ],         [], "SET 1,E", 2),
    (0xCB, 0xCC) : (0, [ SET(1, "H") ],         [], "SET 1,H", 2),
    (0xCB, 0xCD) : (0, [ SET(1, "L") ],         [], "SET 1,L", 2),
    (0xCB, 0xCE) : (0, [],                      [ MR(indirect="HL", action=SET(1)), MW(indirect="HL") ], "SET 1,(HL)", 2),
    (0xCB, 0xCF) : (0, [ SET(1, "A") ],         [], "SET 1,A", 2),
    (0xCB, 0xD0) : (0, [ SET(2, "B") ],         [], "SET 2,B", 2),
    (0xCB, 0xD1) : (0, [ SET(2, "C") ],         [], "SET 2,C", 2),
    (0xCB, 0xD2) : (0, [ SET(2, "D") ],         [], "SET 2,D", 2),
    (0xCB, 0xD3) : (0, [ SET(2, "E") ],         [], "SET 2,E", 2),
    (0xCB, 0xD4) : (0, [ SET(2, "H") ],         [], "SET 2,H", 2),
    (0xCB, 0xD5) : (0, [ SET(2, "L") ],         [], "SET 2,L", 2),
    (0xCB, 0xD6) : (0, [],                      [ MR(indirect="HL", action=SET(2)), MW(indirect="HL") ], "SET 2,(HL)", 2),
    (0xCB, 0xD7) : (0, [ SET(2, "A") ],         [], "SET 2,A", 2),
    (0xCB, 0xD8) : (0, [ SET(3, "B") ],         [], "SET 3,B", 2),
    (0xCB, 0xD9) : (0, [ SET(3, "C") ],         [], "SET 3,C", 2),
    (0xCB, 0xDA) : (0, [ SET(3, "D") ],         [], "SET 3,D", 2),
    (0xCB, 0xDB) : (0, [ SET(3, "E") ],         [], "SET 3,E", 2),
    (0xCB, 0xDC) : (0, [ SET(3, "H") ],         [], "SET 3,H", 2),
    (0xCB, 0xDD) : (0, [ SET(3, "L") ],         [], "SET 3,L", 2),
    (0xCB, 0xDE) : (0, [],                      [ MR(indirect="HL", action=SET(3)), MW(indirect="HL") ], "SET 3,(HL)", 2),
    (0xCB, 0xDF) : (0, [ SET(3, "A") ],         [], "SET 3,A", 2),
    (0xCB, 0xE0) : (0, [ SET(4, "B") ],         [], "SET 4,B", 2),
    (0xCB, 0xE1) : (0, [ SET(4, "C") ],         [], "SET 4,C", 2),
    (0xCB, 0xE2) : (0, [ SET(4, "D") ],         [], "SET 4,D", 2),
    (0xCB, 0xE3) : (0, [ SET(4, "E") ],         [], "SET 4,E", 2),
    (0xCB, 0xE4) : (0, [ SET(4, "H") ],         [], "SET 4,H", 2),
    (0xCB, 0xE5) : (0, [ SET(4, "L") ],         [], "SET 4,L", 2),
    (0xCB, 0xE6) : (0, [],                      [ MR(indirect="HL", action=SET(4)), MW(indirect="HL") ], "SET 4,(HL)", 2),
    (0xCB, 0xE7) : (0, [ SET(4, "A") ],         [], "SET 4,A", 2),
    (0xCB, 0xE8) : (0, [ SET(5, "B") ],         [], "SET 5,B", 2),
    (0xCB, 0xE9) : (0, [ SET(5, "C") ],         [], "SET 5,C", 2),
    (0xCB, 0xEA) : (0, [ SET(5, "D") ],         [], "SET 5,D", 2),
    (0xCB, 0xEB) : (0, [ SET(5, "E") ],         [], "SET 5,E", 2),
    (0xCB, 0xEC) : (0, [ SET(5, "H") ],         [], "SET 5,H", 2),
    (0xCB, 0xED) : (0, [ SET(5, "L") ],         [], "SET 5,L", 2),
    (0xCB, 0xEE) : (0, [],                      [ MR(indirect="HL", action=SET(5)), MW(indirect="HL") ], "SET 5,(HL)", 2),
    (0xCB, 0xEF) : (0, [ SET(5, "A") ],         [], "SET 5,A", 2),
    (0xCB, 0xF0) : (0, [ SET(6, "B") ],         [], "SET 6,B", 2),
    (0xCB, 0xF1) : (0, [ SET(6, "C") ],         [], "SET 6,C", 2),
    (0xCB, 0xF2) : (0, [ SET(6, "D") ],         [], "SET 6,D", 2),
    (0xCB, 0xF3) : (0, [ SET(6, "E") ],         [], "SET 6,E", 2),
    (0xCB, 0xF4) : (0, [ SET(6, "H") ],         [], "SET 6,H", 2),
    (0xCB, 0xF5) : (0, [ SET(6, "L") ],         [], "SET 6,L", 2),
    (0xCB, 0xF6) : (0, [],                      [ MR(indirect="HL", action=SET(6)), MW(indirect="HL") ], "SET 6,(HL)", 2),
    (0xCB, 0xF7) : (0, [ SET(6, "A") ],         [], "SET 6,A", 2),
    (0xCB, 0xF8) : (0, [ SET(7, "B") ],         [], "SET 7,B", 2),
    (0xCB, 0xF9) : (0, [ SET(7, "C") ],         [], "SET 7,C", 2),
    (0xCB, 0xFA) : (0, [ SET(7, "D") ],         [], "SET 7,D", 2),
    (0xCB, 0xFB) : (0, [ SET(7, "E") ],         [], "SET 7,E", 2),
    (0xCB, 0xFC) : (0, [ SET(7, "H") ],         [], "SET 7,H", 2),
    (0xCB, 0xFD) : (0, [ SET(7, "L") ],         [], "SET 7,L", 2),
    (0xCB, 0xFE) : (0, [],                      [ MR(indirect="HL", action=SET(7)), MW(indirect="HL") ], "SET 7,(HL)", 2),
    (0xCB, 0xFF) : (0, [ SET(7, "A") ],         [], "SET 7,A", 2),

    (0xDD, 0x09) : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.B)&0xF)+((state.cpu.reg.IXH)&0xF)+((state.cpu.reg.C+state.cpu.reg.IXL)>>8) > 0xF) else 0),
                 set_flags("--5-3-0C", value=lambda state : state.cpu.reg.B + state.cpu.reg.IXH + ((state.cpu.reg.C+state.cpu.reg.IXL)>>8)),
                 LDr('IX', value=lambda state : (state.cpu.reg.IX + state.cpu.reg.BC)&0xFFFF) ],
                                    [ IO(4, True), IO(3, True) ], "ADD IX,BC", 2),
    (0xDD, 0x19) : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.D)&0xF)+((state.cpu.reg.IXH)&0xF)+((state.cpu.reg.E+state.cpu.reg.IXL)>>8) > 0xF) else 0),
                 set_flags("--5-3-0C", value=lambda state : state.cpu.reg.D + state.cpu.reg.IXH + ((state.cpu.reg.E+state.cpu.reg.IXL)>>8)),
                 LDr('IX', value=lambda state : (state.cpu.reg.IX + state.cpu.reg.DE)&0xFFFF) ],
                                    [ IO(4, True), IO(3, True) ], "ADD IX,DE", 2),
    (0xDD, 0x29) : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.IXH)&0xF)+((state.cpu.reg.IXH)&0xF)+((state.cpu.reg.IXL+state.cpu.reg.IXL)>>8) > 0xF) else 0),
                 set_flags("--5-3-0C", value=lambda state : state.cpu.reg.IXH + state.cpu.reg.IXH + ((state.cpu.reg.IXL+state.cpu.reg.IXL)>>8)),
                 LDr('IX', value=lambda state : (state.cpu.reg.IX + state.cpu.reg.IX)&0xFFFF) ],
                                    [ IO(4, True), IO(3, True) ], "ADD IX,IX", 2),
    (0xDD, 0x39) : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.SPH)&0xF)+((state.cpu.reg.IXH)&0xF)+((state.cpu.reg.SPL+state.cpu.reg.IXL)>>8) > 0xF) else 0),
                 set_flags("--5-3-0C", value=lambda state : state.cpu.reg.SPH + state.cpu.reg.IXH + ((state.cpu.reg.SPL+state.cpu.reg.IXL)>>8)),
                 LDr('IX', value=lambda state : (state.cpu.reg.IX + state.cpu.reg.SP)&0xFFFF) ],
                                    [ IO(4, True), IO(3, True) ], "ADD IX,SP", 2),
    (0xDD, 0x21) : (0, [],                [ OD(), OD(action=LDr('IX')) ], "LD IX,nn", 4),
    (0xDD, 0x22) : (0, [],                [ OD(key="address"),
                                            OD(key="address", compound=high_after_low),
                                            MW(source="IXL"),
                                            MW(source="IXH")], "LD (nn),IX", 4),
    (0xDD, 0x23) : (0, [ LDr('IX', value=lambda state : (state.cpu.reg.IX + 1)&0xFFFF) ],
                                    [], "INC IX", 2),
    (0xDD, 0x2A) : (0, [],                [ OD(key="address"),
                                            OD(key="address", compound=high_after_low),
                                            MR(action=LDr('IXL')), MR(action=LDr('IXH')) ], "LD IX,(nn)", 4),
    (0xDD, 0x2B) : (0, [ LDr('IX', value=lambda state : (state.cpu.reg.IX - 1)&0xFFFF) ],
                                    [], "DEC IX", 2),
    (0xDD, 0x34) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IX') }),
                                            MR(action=do_each(
                                                force_flag('H', lambda  state,v : 1 if ((v&0xF)+1 > 0xF) else 0),
                                                set_flags("SZ5-3V0-", value=lambda state, v : v + 1, key="value")),
                                               incaddr=False),
                                            MW() ], "INC (IX+d)", 3),
    (0xDD, 0x35) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IX') }),
                                            MR(action=do_each(
                                                force_flag('H', lambda  state,v : 1 if ((v&0xF)-1 < 0x0) else 0),
                                                set_flags("SZ5H3V1-", value=lambda state, v : v - 1, key="value")),
                                               incaddr=False),
                                            MW() ], "DEC (IX+d)", 3),
    (0xDD, 0x36) : (0, [],                [ OD(key='address', signed=True),
                                                OD(key='value'),
                                                IO(5, True, transform={ 'address' : add_register('IX') }),
                                                MW() ], "LD (IX+d),n", 3),
    (0xDD, 0x46) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IX') }),
                                                MR(action=LDr("B")) ], "LD B,(IX+d)"),
    (0xDD, 0x4E) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IX') }),
                                                MR(action=LDr("C")) ], "LD C,(IX+d)", 3),
    (0xDD, 0x56) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IX') }),
                                                MR(action=LDr("D")) ], "LD D,(IX+d)", 3),
    (0xDD, 0x5E) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IX') }),
                                                MR(action=LDr("E")) ], "LD E,(IX+d)", 3),
    (0xDD, 0x66) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IX') }),
                                                MR(action=LDr("H")) ], "LD H,(IX+d)", 3),
    (0xDD, 0x6E) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IX') }),
                                                MR(action=LDr("L")) ], "LD L,(IX+d)", 3),
    (0xDD, 0x70) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IX') }),
                                                MW(source="B") ], "LD (IX+d),B", 3),
    (0xDD, 0x71) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IX') }),
                                                MW(source="C") ], "LD (IX+d),C", 3),
    (0xDD, 0x72) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IX') }),
                                                MW(source="D") ], "LD (IX+d),D", 3),
    (0xDD, 0x73) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IX') }),
                                                MW(source="E") ], "LD (IX+d),E"),
    (0xDD, 0x74) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IX') }),
                                                MW(source="H") ], "LD (IX+d),H", 3),
    (0xDD, 0x75) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IX') }),
                                                MW(source="L") ], "LD (IX+d),L", 3),
    (0xDD, 0x77) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IX') }),
                                                MW(source="A") ], "LD (IX+d),A", 3),
    (0xDD, 0x7E) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IX') }),
                                                MR(action=LDr("A")) ], "LD A,(IX+d)", 3),
    (0xDD, 0x86) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IX') }),
                                            MR(action=do_each(
                                                force_flag('H', lambda  state,v : 1 if (((state.cpu.reg.A)&0xF)+(v&0xF) > 0xF) else 0),
                                                set_flags("SZ5H3V0C",
                                                value=lambda state, v : state.cpu.reg.A + v,
                                                dest="A"))) ], "ADD (IX+d)", 3),
    (0xDD, 0x8E) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IX') }),
                                            MR(action=do_each(
                                                force_flag('H', lambda  state,v : 1 if (((state.cpu.reg.A)&0xF)+(v&0xF)+state.cpu.reg.getflag('C') > 0xF) else 0),
                                                set_flags("SZ5H3V0C",
                                                value=lambda state, v : state.cpu.reg.A + v + state.cpu.reg.getflag('C'),
                                                dest="A"))) ], "ADC (IX+d)", 3),
    (0xDD, 0x96) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IX') }),
                                            MR(action=do_each(
                                                force_flag('H', lambda  state,v : 1 if (((state.cpu.reg.A)&0xF)-(v&0xF) < 0x0) else 0),
                                                set_flags("SZ5H3V1C",
                                               value=lambda state, v : state.cpu.reg.A - v,
                                               dest="A"))) ], "SUB (IX+d)", 3),
    (0xDD, 0x9E) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IX') }),
                                            MR(action=do_each(
                                            force_flag('H', lambda  state,v : 1 if (((state.cpu.reg.A)&0xF)-(v&0xF) - state.cpu.reg.getflag('C') < 0x0) else 0),
                                            set_flags("SZ5H3V1C",
                                               value=lambda state, v : state.cpu.reg.A - v - state.cpu.reg.getflag('C'),
                                               dest="A"))) ], "SBC (IX+d)", 3),
    (0xDD, 0xA6) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IX') }),
                                            MR(action=set_flags("SZ513P00",
                                               value=lambda state, v : state.cpu.reg.A & v,
                                               dest="A")) ], "AND (IX+d)", 3),
    (0xDD, 0xAE) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IX') }),
                                            MR(action=set_flags("SZ503P00",
                                               value=lambda state, v : state.cpu.reg.A ^ v,
                                               dest="A")) ], "XOR (IX+d)", 3),
    (0xDD, 0xB6) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IX') }),
                                            MR(action=set_flags("SZ503P00",
                                               value=lambda state, v : state.cpu.reg.A | v,
                                               dest="A")) ], "OR (IX+d)", 3),
    (0xDD, 0xBE) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IX') }),
                                            MR(action=set_flags("SZ5H3V1C",
                                               value=lambda state, v : state.cpu.reg.A - v,)) ], "CP (IX+d)", 3),
    (0xDD, 0xCB) : (0, [],                [ OD(key='address', signed=True),
                                            IO(1, True, transform={'address' : add_register('IX') }),
                                            OCF(prefix=(0xDD, 0xCB)) ], "-- second and third bytes of 4 byte op-code"),
    (0xDD, 0xE1) : (0, [],                [ SR(), SR(action=LDr("IX")) ], "POP IX", 2),
    (0xDD, 0xE3) : (0, [ RRr('H','IXH'), RRr('L','IXL') ],
                        [ SR(), SR(action=LDr("IX"), extra=1), SW(key="H"), SW(key="L", extra=2) ], "EX (SP),IX"),
    (0xDD, 0xE5) : (1, [],                [ SW(source="IXH"), SW(source="IXL") ], "PUSH IX", 2),
    (0xDD, 0xE9) : (0, [ JP(source="IX") ], [], "JP (IX)", 2),
    (0xDD, 0xF9) : (0, [LDrs('SP','IX'),],[], "LD SP,IX", 2),

    (0xED, 0x40) : (0, [],                [ PR(high="B", low="C", dest="B",
                                                   action=set_flags("SZ503P0-")) ], "IN B,(C)", 2),
    (0xED, 0x41) : (0, [],                [ PW(high="B", low="C", source="B") ], "OUT (C),B", 2),
    (0xED, 0x42) : (0, SBC16('BC'),      [ IO(4, True), IO(3, True) ], "SBC HL,BC", 2),
    (0xED, 0x43) : (0, [],                [ OD(key="address"),
                                            OD(key="address",
                                            compound=high_after_low),
                                            MW(source="C"), MW(source="B") ], "LD (nn),BC", 4),
    (0xED, 0x44) : (0, [ set_flags("SZ513V11", value=lambda state : (-state.cpu.reg.A)&0xFF, dest='A') ],
                                         [], "NEG", 2),
    (0xED, 0x45) : (0, [],               [ SR(), SR(action=do_each(restore_iff(), JP())) ], "RETN", 2),
    (0xED, 0x46) : (0, [ im(0) ],        [], "IM0", 2),
    (0xED, 0x47) : (0, [LDrs('I', 'A')], [], "LD I,A", 2),
    (0xED, 0x48) : (0, [],                [ PR(high="B", low="C", dest="C",
                                                   action=set_flags("SZ503P0-")) ], "IN C,(C)", 2),
    (0xED, 0x49) : (0, [],                [ PW(high="B", low="C", source="C") ], "OUT (C),C", 2),
    (0xED, 0x4B) : (0, [],                [ OD(key="address"),
                                            OD(key="address", compound=high_after_low),
                                            MR(action=LDr('C')), MR(action=LDr('B')) ], "LD BC,(nn)", 4),
    (0xED, 0x4A) : (0, ADC16('BC'),      [ IO(4, True), IO(3, True) ], "ADC HL,BC", 2),
    (0xED, 0x4D) : (0, [],               [ SR(), SR(action=JP()) ], "RETI", 2),
    (0xED, 0x4F) : (0, [LDrs('R', 'A'),], [], "LD R,A", 2),
    (0xED, 0x50) : (0, [],                [ PR(high="B", low="C", dest="D",
                                                   action=set_flags("SZ503P0-")) ], "IN D,(C)", 2),
    (0xED, 0x51) : (0, [],                [ PW(high="B", low="C", source="D") ], "OUT (C),D", 2),
    (0xED, 0x52) : (0, SBC16('DE'),      [ IO(4, True), IO(3, True) ], "SBC HL,DE", 2),
    (0xED, 0x53) : (0, [],                [ OD(key="address"),
                                            OD(key="address", compound=high_after_low),
                                            MW(source="E"),
                                            MW(source="D") ], "LD (nn),DE", 4),
    (0xED, 0x56) : (0, [ im(1) ],        [], "IM1", 2),
    (0xED, 0x57) : (0, [LDrs('A', 'I'), set_flags("SZ503*0-", source='I') ], [], "LD A,I", 2),
    (0xED, 0x58) : (0, [],                [ PR(high="B", low="C", dest="E",
                                                   action=set_flags("SZ503P0-")) ], "IN E,(C)", 2),
    (0xED, 0x59) : (0, [],                [ PW(high="B", low="C", source="E") ], "OUT (C),E", 2),
    (0xED, 0x5A) : (0, ADC16('DE'),      [ IO(4, True), IO(3, True) ], "ADC HL,DE", 2),
    (0xED, 0x5B) : (0, [],                [ OD(key="address"),
                                            OD(key="address", compound=high_after_low),
                                            MR(action=LDr('E')), MR(action=LDr('D')) ], "LD DE,(nn)", 4),
    (0xED, 0x5E) : (0, [ im(2) ],        [], "IM2", 2),
    (0xED, 0x5F) : (0, [LDrs('A', 'R'), set_flags("SZ503*0-", source='R') ], [], "LD A,R", 2),
    (0xED, 0x60) : (0, [],                [ PR(high="B", low="C", dest="H",
                                                   action=set_flags("SZ503P0-")) ], "IN H,(C)", 2),
    (0xED, 0x61) : (0, [],                [ PW(high="B", low="C", source="H") ], "OUT (C),H", 2),
    (0xED, 0x62) : (0, SBC16('HL'),      [ IO(4, True), IO(3, True) ], "SBC HL,HL", 2),
    (0xED, 0x67) : (0, [],               [ MR(indirect="HL",
                                              action=do_each(
                                                  RRr("value", value=lambda state,v : (v >> 4) | (state.cpu.reg.A << 4)),
                                                  set_flags("SZ503P0-", value=lambda state,v : (v&0x0F), dest="A", key=None))),
                                            IO(4, True),
                                            MW(indirect="HL") ], "RRD", 2),
    (0xED, 0x68) : (0, [],               [ PR(high="B", low="C", dest="L",
                                                  action=set_flags("SZ503P0-")) ], "IN L,(C)", 2),
    (0xED, 0x69) : (0, [],                [ PW(high="B", low="C", source="L") ], "OUT (C),L", 2),
    (0xED, 0x6A) : (0, ADC16('HL'),      [ IO(4, True), IO(3, True) ], "ADC HL,HL", 2),
    (0xED, 0x6F) : (0, [],               [ MR(indirect="HL",
                                              action=do_each(
                                                  RRr("value", value=lambda state,v : (v << 4) | (state.cpu.reg.A&0x0F)),
                                                  set_flags("SZ503P0-", value=lambda state,v : (v >> 4), dest="A", key=None))),
                                            IO(4, True),
                                            MW(indirect="HL") ], "RLD", 2),
    (0xED, 0x70) : (0, [],                [ PR(high="B", low="C", dest="F",
                                                   action=set_flags("SZ503P0-")) ], "IN F,(C) (undocumented)", 2),
    (0xED, 0x71) : (0, [],                [ PW(high="B", low="C", source="F") ], "OUT (C),F (undocumented)", 2),
    (0xED, 0x72) : (0, SBC16('SP'),      [ IO(4, True), IO(3, True) ], "SBC HL,SP", 2),
    (0xED, 0x73) : (0, [],                [ OD(key="address"),
                                            OD(key="address", compound=high_after_low),
                                            MW(source="SPL"),
                                            MW(source="SPH") ], "LD (nn),SP", 2),
    (0xED, 0x78) : (0, [],                [ PR(high="B", low="C", dest="A",
                                                   action=set_flags("SZ503P0-")) ], "IN A,(C)", 2),
    (0xED, 0x79) : (0, [],                [ PW(high="B", low="C", source="A") ], "OUT (C),A", 2),
    (0xED, 0x7A) : (0, ADC16('SP'),      [ IO(4, True), IO(3, True) ], "ADC HL,SP", 2),
    (0xED, 0x7B) : (0, [],                [ OD(key="address"),
                                            OD(key="address", compound=high_after_low),
                                            MR(action=LDr('SPL')), MR(action=LDr('SPH')) ], "LD SP,(nn)", 4),
    (0xED, 0xA0) : (0, [],                [ MR(indirect="HL"),
                                            MW(indirect="DE",
                                                extra=2,
                                                action=do_each(set_flags("--50310-", value=lambda state,_ : state.kwargs['value'] + state.cpu.reg.A),
                                                                inc("HL"),
                                                                inc("DE"),
                                                                dec("BC"),
                                                                on_zero("BC", clear_flag("V")))) ], "LDI", 2),
    (0xED, 0xA1) : (0, [],                [ MR(indirect="HL"),
                                            IO(5, True, transform={'value' : subfrom() },
                                                   action=do_each(set_flags("-Z50311-"),
                                                                  inc("HL"),
                                                                  dec("BC"),
                                                                  on_zero("BC", clear_flag("V")))) ], "CPI", 2),
    (0xED, 0xA2) : (0, [],                [ PR(high="B", low="C"),
                                            MW(indirect="HL",
                                               action=do_each(inc("HL"),
                                                              dec("B"),
                                                              set_flags("SZ503P0-",
                                                                        source="B"))) ], "INI", 2),
    (0xED, 0xA3) : (0, [],                [ MR(indirect="HL"),
                                            PW(low="C", high="B",
                                               action=do_each(inc("HL"),
                                                              dec("B"),
                                                              set_flags("SZ503P0-",
                                                                        source="B"))) ], "OUTI", 2),
    (0xED, 0xA8) : (0, [],                [ MR(indirect="HL"),
                                            MW(indirect="DE",
                                                extra=2,
                                                action=do_each(set_flags("--50310-", value=lambda state,_ : state.kwargs['value'] + state.cpu.reg.A),
                                                                dec("HL"),
                                                                dec("DE"),
                                                                dec("BC"),
                                                                on_zero("BC", clear_flag("V")))) ], "LDD", 2),
    (0xED, 0xA9) : (0, [],                [ MR(indirect="HL"),
                                            IO(5, True, transform={'value' : subfrom() },
                                                   action=do_each(set_flags("-Z50311-"),
                                                                  dec("HL"),
                                                                  dec("BC"),
                                                                  on_zero("BC", clear_flag("V")))) ], "CPD", 2),
    (0xED, 0xAA) : (0, [],                [ PR(high="B", low="C"),
                                            MW(indirect="HL",
                                               action=do_each(dec("HL"),
                                                              dec("B"),
                                                              set_flags("SZ503P0-",
                                                                        source="B"))) ], "IND", 2),
    (0xED, 0xAB) : (0, [],                [ MR(indirect="HL"),
                                            PW(low="C", high="B",
                                               action=do_each(dec("HL"),
                                                              dec("B"),
                                                              set_flags("SZ503P0-",
                                                                        source="B"))) ], "OUTD", 2),
    (0xED, 0xB0) : (0, [],                [ MR(indirect="HL"),
                                            MW(indirect="DE",
                                                extra=2,
                                                action=do_each(set_flags("--50310-", value=lambda state,_ : state.kwargs['value'] + state.cpu.reg.A),
                                                                inc("HL"),
                                                                inc("DE"),
                                                                dec("BC"),
                                                                on_zero("BC", clear_flag("V")),
                                                                on_zero("BC", early_abort()))),
                                            IO(5, True, action=do_each(dec("PC"), dec("PC"))) ], "LDIR", 2),
    (0xED, 0xB1) : (0, [],                [ MR(indirect="HL"),
                                            IO(5, True, transform={'value' : subfrom() },
                                                   action=do_each(set_flags("-Z50311-"),
                                                                  inc("HL"),
                                                                  dec("BC"),
                                                                  on_zero("BC", clear_flag("V")),
                                                                  on_zero("BC", early_abort()),
                                                                  on_flag('Z', early_abort()))),
                                            IO(5, True, action=do_each(dec("PC"), dec("PC"))) ], "CPIR", 2),
    (0xED, 0xB2) : (0, [],                [ PR(high="B", low="C"),
                                            MW(indirect="HL",
                                               action=do_each(inc("HL"),
                                                              dec("B"),
                                                              set_flags("SZ503P0-",
                                                                        source="B"),
                                                              on_flag('Z', early_abort()))),
                                            IO(5, True, action=do_each(dec("PC"), dec("PC")))], "INIR", 2),
    (0xED, 0xB3) : (0, [],                [ MR(indirect="HL"),
                                            PW(low="C", high="B",
                                               action=do_each(inc("HL"),
                                                              dec("B"),
                                                              set_flags("SZ503P0-",
                                                                        source="B"),
                                                              on_flag('Z', early_abort()))),
                                            IO(5, True, action=do_each(dec("PC"), dec("PC")))], "OUTIR", 2),
    (0xED, 0xB8) : (0, [],                [ MR(indirect="HL"),
                                            MW(indirect="DE",
                                                extra=2,
                                                action=do_each(set_flags("--50310-", value=lambda state,_ : state.kwargs['value'] + state.cpu.reg.A),
                                                                dec("HL"),
                                                                dec("DE"),
                                                                dec("BC"),
                                                                on_zero("BC", clear_flag("V")),
                                                                on_zero("BC", early_abort()))),
                                            IO(5, True, action=do_each(dec("PC"), dec("PC"))) ], "LDDR", 2),
    (0xED, 0xB9) : (0, [],                [ MR(indirect="HL"),
                                            IO(5, True, transform={'value' : subfrom() },
                                                   action=do_each(set_flags("-Z50311-"),
                                                                  dec("HL"),
                                                                  dec("BC"),
                                                                  on_zero("BC", clear_flag("V")),
                                                                  on_zero("BC", early_abort()),
                                                                  on_flag('Z', early_abort()))),
                                                IO(5, True, action=do_each(dec("PC"), dec("PC"))) ], "CPDR", 2),
    (0xED, 0xBA) : (0, [],                [ PR(high="B", low="C"),
                                            MW(indirect="HL",
                                               action=do_each(dec("HL"),
                                                              dec("B"),
                                                              set_flags("SZ503P0-",
                                                                        source="B"),
                                                              on_flag('Z', early_abort()))),
                                            IO(5, True, action=do_each(dec("PC"), dec("PC")))], "INDR", 2),
    (0xED, 0xBB) : (0, [],                [ MR(indirect="HL"),
                                            PW(low="C", high="B",
                                               action=do_each(dec("HL"),
                                                              dec("B"),
                                                              set_flags("SZ503P0-",
                                                                        source="B"),
                                                              on_flag('Z', early_abort()))),
                                            IO(5, True, action=do_each(dec("PC"), dec("PC")))], "OUTDR", 2),

    (0xFD, 0x09) : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.B)&0xF)+((state.cpu.reg.IYH)&0xF)+((state.cpu.reg.C+state.cpu.reg.IYL)>>8) > 0xF) else 0),
                 set_flags("--5-3-0C", value=lambda state : state.cpu.reg.B + state.cpu.reg.IYH + ((state.cpu.reg.C+state.cpu.reg.IYL)>>8)),
                 LDr('IY', value=lambda state : (state.cpu.reg.IY + state.cpu.reg.BC)&0xFFFF) ],
                                    [ IO(4, True), IO(3, True) ], "ADD IY,BC", 2),
    (0xFD, 0x19) : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.D)&0xF)+((state.cpu.reg.IYH)&0xF)+((state.cpu.reg.E+state.cpu.reg.IYL)>>8) > 0xF) else 0),
                 set_flags("--5-3-0C", value=lambda state : state.cpu.reg.D + state.cpu.reg.IYH + ((state.cpu.reg.E+state.cpu.reg.IYL)>>8)),
                 LDr('IY', value=lambda state : (state.cpu.reg.IY + state.cpu.reg.DE)&0xFFFF) ],
                                    [ IO(4, True), IO(3, True) ], "ADD IY,DE", 2),
    (0xFD, 0x23) : (0, [ LDr('IY', value=lambda state : (state.cpu.reg.IY + 1)&0xFFFF) ],
                                    [], "INC IY", 2),
    (0xFD, 0x29) : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.IYH)&0xF)+((state.cpu.reg.IYH)&0xF)+((state.cpu.reg.IYL+state.cpu.reg.IYL)>>8) > 0xF) else 0),
                 set_flags("--5-3-0C", value=lambda state : state.cpu.reg.IYH + state.cpu.reg.IYH + ((state.cpu.reg.IYL+state.cpu.reg.IYL)>>8)),
                 LDr('IY', value=lambda state : (state.cpu.reg.IY + state.cpu.reg.IY)&0xFFFF) ],
                                    [ IO(4, True), IO(3, True) ], "ADD IY,IY", 2),
    (0xFD, 0x2B) : (0, [ LDr('IY', value=lambda state : (state.cpu.reg.IY - 1)&0xFFFF) ],
                                    [], "DEC IY", 2),
    (0xFD, 0x39) : (0, [ force_flag('H', lambda  state : 1 if (((state.cpu.reg.SPH)&0xF)+((state.cpu.reg.IYH)&0xF)+((state.cpu.reg.SPL+state.cpu.reg.IYL)>>8) > 0xF) else 0),
                 set_flags("--5-3-0C", value=lambda state : state.cpu.reg.SPH + state.cpu.reg.IYH + ((state.cpu.reg.SPL+state.cpu.reg.IYL)>>8)),
                 LDr('IY', value=lambda state : (state.cpu.reg.IY + state.cpu.reg.SP)&0xFFFF) ],
                                    [ IO(4, True), IO(3, True) ], "ADD IY,SP", 2),
    (0xFD, 0x21) : (0, [],                [ OD(), OD(action=LDr('IY')) ], "LD IY,nn", 4),
    (0xFD, 0x22) : (0, [],                [ OD(key="address"),
                                            OD(key="address"),
                                            MW(source="IYL"),
                                            MW(source="IYH") ], "LD (nn),IY", 4),
    (0xFD, 0x2A) : (0, [],                [ OD(key="address"),
                                            OD(key="address"),
                                            MR(action=LDr('IYL')), MR(action=LDr('IYH')) ], "LD IY,(nn)", 4),
    (0xFD, 0x34) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IY') }),
                                            MR(action=do_each(
                                                force_flag('H', lambda  state,v : 1 if ((v&0xF)+1 > 0xF) else 0),
                                                set_flags("SZ5-3V0-", value=lambda state, v : v + 1, key="value")),
                                               incaddr=False),
                                            MW() ], "INC (IY+d)", 3),
    (0xFD, 0x35) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IY') }),
                                            MR(action=do_each(
                                                force_flag('H', lambda  state,v : 1 if ((v&0xF)-1 < 0x0) else 0),
                                                set_flags("SZ5H3V1-", value=lambda state, v : v - 1, key="value")),
                                               incaddr=False),
                                            MW() ], "DEC (IY+d)", 3),
    (0xFD, 0x36) : (0, [],                [ OD(key='address', signed=True),
                                                OD(key='value'),
                                                IO(5, True, transform={ 'address' : add_register('IY') }),
                                                MW() ], "LD (IY+d),n", 4),
    (0xFD, 0x46) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IY') }),
                                                MR(action=LDr("B")) ], "LD B,(IY+d)", 3),
    (0xFD, 0x4E) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IY') }),
                                                MR(action=LDr("C")) ], "LD C,(IY+d)", 3),
    (0xFD, 0x56) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IY') }),
                                                MR(action=LDr("D")) ], "LD D,(IY+d)", 3),
    (0xFD, 0x5E) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IY') }),
                                                MR(action=LDr("E")) ], "LD E,(IY+d)", 3),
    (0xFD, 0x66) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IY') }),
                                                MR(action=LDr("H")) ], "LD H,(IY+d)", 3),
    (0xFD, 0x6E) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IY') }),
                                                MR(action=LDr("L")) ], "LD L,(IY+d)", 3),
    (0xFD, 0x70) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IY') }),
                                                MW(source="B") ], "LD (IY+d),B", 3),
    (0xFD, 0x71) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IY') }),
                                                MW(source="C") ], "LD (IY+d),C", 3),
    (0xFD, 0x72) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IY') }),
                                                MW(source="D") ], "LD (IY+d),D", 3),
    (0xFD, 0x73) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IY') }),
                                                MW(source="E") ], "LD (IY+d),E", 3),
    (0xFD, 0x74) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IY') }),
                                                MW(source="H") ], "LD (IY+d),H", 3),
    (0xFD, 0x75) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IY') }),
                                                MW(source="L") ], "LD (IY+d),L", 3),
    (0xFD, 0x77) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IY') }),
                                                MW(source="A") ], "LD (IY+d),A", 3),
    (0xFD, 0x7E) : (0, [],                [ OD(key='address', signed=True),
                                                IO(5, True, transform={ 'address' : add_register('IY') }),
                                                MR(action=LDr("A")) ], "LD A,(IY+d)", 3),
    (0xFD, 0x86) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IY') }),
                                            MR(action=do_each(
                                                force_flag('H', lambda  state,v : 1 if (((state.cpu.reg.A)&0xF)+(v&0xF) > 0xF) else 0),
                                                set_flags("SZ5H3V0C",
                                                value=lambda state, v : state.cpu.reg.A + v,
                                                dest="A"))) ], "ADD (IY+d)", 3),
    (0xFD, 0x8E) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IY') }),
                                            MR(action=do_each(
                                                force_flag('H', lambda  state,v : 1 if (((state.cpu.reg.A)&0xF)+(v&0xF)+state.cpu.reg.getflag('C') > 0xF) else 0),
                                                set_flags("SZ5H3V0C",
                                                value=lambda state, v : state.cpu.reg.A + v + state.cpu.reg.getflag('C'),
                                                dest="A"))) ], "ADC (IY+d)", 3),
    (0xFD, 0x96) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IY') }),
                                            MR(action=do_each(
                                                force_flag('H', lambda  state,v : 1 if (((state.cpu.reg.A)&0xF)-(v&0xF) < 0x0) else 0),
                                                set_flags("SZ5H3V1C",
                                               value=lambda state, v : state.cpu.reg.A - v,
                                               dest="A"))) ], "SUB (IY+d)", 3),
    (0xFD, 0x9E) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IY') }),
                                            MR(action=do_each(
                                            force_flag('H', lambda  state,v : 1 if (((state.cpu.reg.A)&0xF)-(v&0xF) - state.cpu.reg.getflag('C') < 0x0) else 0),
                                            set_flags("SZ5H3V1C",
                                               value=lambda state, v : state.cpu.reg.A - v - state.cpu.reg.getflag('C'),
                                               dest="A"))) ], "SBC (IY+d)", 3),
    (0xFD, 0xA6) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IY') }),
                                            MR(action=set_flags("SZ513P00",
                                               value=lambda state, v : state.cpu.reg.A & v,
                                               dest="A")) ], "AND (IY+d)", 3),
    (0xFD, 0xAE) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IY') }),
                                            MR(action=set_flags("SZ503P00",
                                               value=lambda state, v : state.cpu.reg.A ^ v,
                                               dest="A")) ], "XOR (IY+d)", 3),
    (0xFD, 0xB6) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IY') }),
                                            MR(action=set_flags("SZ503P00",
                                               value=lambda state, v : state.cpu.reg.A | v,
                                               dest="A")) ], "OR (IY+d)", 3),
    (0xFD, 0xBE) : (0, [],                [ OD(key='address', signed=True),
                                            IO(5, True, transform={'address' : add_register('IY') }),
                                            MR(action=set_flags("SZ5H3V1C",
                                               value=lambda state, v : state.cpu.reg.A - v,)) ], "CP (IY+d)", 3),
    (0xFD, 0xCB) : (0, [],                [ OD(key='address', signed=True),
                                            IO(1, True, transform={'address' : add_register('IY') }),
                                            OCF(prefix=(0xFD, 0xCB)) ], "", 0),
    (0xFD, 0xE1) : (0, [],                [ SR(), SR(action=LDr("IY")) ], "POP IY", 2),
    (0xFD, 0xE3) : (0, [ RRr('H','IYH'), RRr('L','IYL') ],
                        [ SR(), SR(action=LDr("IY"), extra=1), SW(key="H"), SW(key="L", extra=2) ], "EX (SP),IY", 2),
    (0xFD, 0xE5) : (1, [],                [ SW(source="IYH"), SW(source="IYL") ], "PUSH IY", 2),
    (0xFD, 0xE9) : (0, [ JP(source="IY") ], [], "JP (IY)", 2),
    (0xFD, 0xF9) : (0, [LDrs('SP','IY'),],[], "LD SP,IY", 2),

    (0xDD, 0xCB, 0x06) : (0, [], [ MR(action=RLC(), incaddr=False), MW() ], "RLC (IX+d)", 4),
    (0xDD, 0xCB, 0x0E) : (0, [], [ MR(action=RRC(), incaddr=False), MW() ], "RRC (IX+d)", 4),
    (0xDD, 0xCB, 0x16) : (0, [], [ MR(action=RL(), incaddr=False), MW() ], "RL (IX+d)", 4),
    (0xDD, 0xCB, 0x1E) : (0, [], [ MR(action=RR(), incaddr=False), MW() ], "RR (IX+d)", 4),
    (0xDD, 0xCB, 0x26) : (0, [], [ MR(action=SLA(), incaddr=False), MW() ], "SLA (IX+d)", 4),
    (0xDD, 0xCB, 0x2E) : (0, [], [ MR(action=SRA(), incaddr=False), MW() ], "SRA (IX+d)", 4),
    (0xDD, 0xCB, 0x36) : (0, [], [ MR(action=SL1(), incaddr=False), MW() ], "SL1 (IX+d) (undocumemnted)", 4),
    (0xDD, 0xCB, 0x3E) : (0, [], [ MR(action=SRL(), incaddr=False), MW() ], "SRA (IX+d)", 4),
    (0xDD, 0xCB, 0x46) : (0, [], [ MR(action=BIT(0)) ], "BIT 0,(IX+d)", 4),
    (0xDD, 0xCB, 0x4E) : (0, [], [ MR(action=BIT(1)) ], "BIT 1,(IX+d)", 4),
    (0xDD, 0xCB, 0x56) : (0, [], [ MR(action=BIT(2)) ], "BIT 2,(IX+d)", 4),
    (0xDD, 0xCB, 0x5E) : (0, [], [ MR(action=BIT(3)) ], "BIT 3,(IX+d)", 4),
    (0xDD, 0xCB, 0x66) : (0, [], [ MR(action=BIT(4)) ], "BIT 4,(IX+d)", 4),
    (0xDD, 0xCB, 0x6E) : (0, [], [ MR(action=BIT(5)) ], "BIT 5,(IX+d)", 4),
    (0xDD, 0xCB, 0x76) : (0, [], [ MR(action=BIT(6)) ], "BIT 6,(IX+d)", 4),
    (0xDD, 0xCB, 0x7E) : (0, [], [ MR(action=BIT(7)) ], "BIT 7,(IX+d)", 4),
    (0xDD, 0xCB, 0x86) : (0, [], [ MR(action=RES(0), incaddr=False), MW() ], "RES 0,(IX+d)", 4),
    (0xDD, 0xCB, 0x8E) : (0, [], [ MR(action=RES(1), incaddr=False), MW() ], "RES 1,(IX+d)", 4),
    (0xDD, 0xCB, 0x96) : (0, [], [ MR(action=RES(2), incaddr=False), MW() ], "RES 2,(IX+d)", 4),
    (0xDD, 0xCB, 0x9E) : (0, [], [ MR(action=RES(3), incaddr=False), MW() ], "RES 3,(IX+d)", 4),
    (0xDD, 0xCB, 0xA6) : (0, [], [ MR(action=RES(4), incaddr=False), MW() ], "RES 4,(IX+d)", 4),
    (0xDD, 0xCB, 0xAE) : (0, [], [ MR(action=RES(5), incaddr=False), MW() ], "RES 5,(IX+d)", 4),
    (0xDD, 0xCB, 0xB6) : (0, [], [ MR(action=RES(6), incaddr=False), MW() ], "RES 6,(IX+d)", 4),
    (0xDD, 0xCB, 0xBE) : (0, [], [ MR(action=RES(7), incaddr=False), MW() ], "RES 7,(IX+d)", 4),
    (0xDD, 0xCB, 0xC6) : (0, [], [ MR(action=SET(0), incaddr=False), MW() ], "SET 0,(IX+d)", 4),
    (0xDD, 0xCB, 0xCE) : (0, [], [ MR(action=SET(1), incaddr=False), MW() ], "SET 1,(IX+d)", 4),
    (0xDD, 0xCB, 0xD6) : (0, [], [ MR(action=SET(2), incaddr=False), MW() ], "SET 2,(IX+d)", 4),
    (0xDD, 0xCB, 0xDE) : (0, [], [ MR(action=SET(3), incaddr=False), MW() ], "SET 3,(IX+d)", 4),
    (0xDD, 0xCB, 0xE6) : (0, [], [ MR(action=SET(4), incaddr=False), MW() ], "SET 4,(IX+d)", 4),
    (0xDD, 0xCB, 0xEE) : (0, [], [ MR(action=SET(5), incaddr=False), MW() ], "SET 5,(IX+d)", 4),
    (0xDD, 0xCB, 0xF6) : (0, [], [ MR(action=SET(6), incaddr=False), MW() ], "SET 6,(IX+d)", 4),
    (0xDD, 0xCB, 0xFE) : (0, [], [ MR(action=SET(7), incaddr=False), MW() ], "SET 7,(IX+d)", 4),

    (0xFD, 0xCB, 0x06) : (0, [], [ MR(action=RLC(), incaddr=False), MW() ], "RLC (IY+d)", 4),
    (0xFD, 0xCB, 0x0E) : (0, [], [ MR(action=RRC(), incaddr=False), MW() ], "RRC (IY+d)", 4),
    (0xFD, 0xCB, 0x16) : (0, [], [ MR(action=RL(), incaddr=False), MW() ], "RL (IY+d)", 4),
    (0xFD, 0xCB, 0x1E) : (0, [], [ MR(action=RR(), incaddr=False), MW() ], "RR (IY+d)", 4),
    (0xFD, 0xCB, 0x26) : (0, [], [ MR(action=SLA(), incaddr=False), MW() ], "SLA (IY+d)", 4),
    (0xFD, 0xCB, 0x2E) : (0, [], [ MR(action=SRA(), incaddr=False), MW() ], "SRA (IY+d)", 4),
    (0xFD, 0xCB, 0x36) : (0, [], [ MR(action=SL1(), incaddr=False), MW() ], "SL1 (IY+d) (undocumemnted)", 4),
    (0xFD, 0xCB, 0x3E) : (0, [], [ MR(action=SRL(), incaddr=False), MW() ], "SRA (IY+d)", 4),
    (0xFD, 0xCB, 0x46) : (0, [], [ MR(action=BIT(0)) ], "BIT 0,(IY+d)", 4),
    (0xFD, 0xCB, 0x4E) : (0, [], [ MR(action=BIT(1)) ], "BIT 1,(IY+d)", 4),
    (0xFD, 0xCB, 0x56) : (0, [], [ MR(action=BIT(2)) ], "BIT 2,(IY+d)", 4),
    (0xFD, 0xCB, 0x5E) : (0, [], [ MR(action=BIT(3)) ], "BIT 3,(IY+d)", 4),
    (0xFD, 0xCB, 0x66) : (0, [], [ MR(action=BIT(4)) ], "BIT 4,(IY+d)", 4),
    (0xFD, 0xCB, 0x6E) : (0, [], [ MR(action=BIT(5)) ], "BIT 5,(IY+d)", 4),
    (0xFD, 0xCB, 0x76) : (0, [], [ MR(action=BIT(6)) ], "BIT 6,(IY+d)", 4),
    (0xFD, 0xCB, 0x7E) : (0, [], [ MR(action=BIT(7)) ], "BIT 7,(IY+d)", 4),
    (0xFD, 0xCB, 0x86) : (0, [], [ MR(action=RES(0), incaddr=False), MW() ], "RES 0,(IY+d)", 4),
    (0xFD, 0xCB, 0x8E) : (0, [], [ MR(action=RES(1), incaddr=False), MW() ], "RES 1,(IY+d)", 4),
    (0xFD, 0xCB, 0x96) : (0, [], [ MR(action=RES(2), incaddr=False), MW() ], "RES 2,(IY+d)", 4),
    (0xFD, 0xCB, 0x9E) : (0, [], [ MR(action=RES(3), incaddr=False), MW() ], "RES 3,(IY+d)", 4),
    (0xFD, 0xCB, 0xA6) : (0, [], [ MR(action=RES(4), incaddr=False), MW() ], "RES 4,(IY+d)", 4),
    (0xFD, 0xCB, 0xAE) : (0, [], [ MR(action=RES(5), incaddr=False), MW() ], "RES 5,(IY+d)", 4),
    (0xFD, 0xCB, 0xB6) : (0, [], [ MR(action=RES(6), incaddr=False), MW() ], "RES 6,(IY+d)", 4),
    (0xFD, 0xCB, 0xBE) : (0, [], [ MR(action=RES(7), incaddr=False), MW() ], "RES 7,(IY+d)", 4),
    (0xFD, 0xCB, 0xC6) : (0, [], [ MR(action=SET(0), incaddr=False), MW() ], "SET 0,(IY+d)", 4),
    (0xFD, 0xCB, 0xCE) : (0, [], [ MR(action=SET(1), incaddr=False), MW() ], "SET 1,(IY+d)", 4),
    (0xFD, 0xCB, 0xD6) : (0, [], [ MR(action=SET(2), incaddr=False), MW() ], "SET 2,(IY+d)", 4),
    (0xFD, 0xCB, 0xDE) : (0, [], [ MR(action=SET(3), incaddr=False), MW() ], "SET 3,(IY+d)", 4),
    (0xFD, 0xCB, 0xE6) : (0, [], [ MR(action=SET(4), incaddr=False), MW() ], "SET 4,(IY+d)", 4),
    (0xFD, 0xCB, 0xEE) : (0, [], [ MR(action=SET(5), incaddr=False), MW() ], "SET 5,(IY+d)", 4),
    (0xFD, 0xCB, 0xF6) : (0, [], [ MR(action=SET(6), incaddr=False), MW() ], "SET 6,(IY+d)", 4),
    (0xFD, 0xCB, 0xFE) : (0, [], [ MR(action=SET(7), incaddr=False), MW() ], "SET 7,(IY+d)", 4),
    }

def decode_instruction(instruction):
    """Decode an instruction code and return a tuple of:
    (extra_time_for_OCF, [list of callables as side-effects of OCF], [ list of new machine states to add to pipeline ], "mnemonic", # bytes)"""
    if instruction in INSTRUCTION_STATES:
        return INSTRUCTION_STATES[instruction][:3]
    raise UnrecognisedInstructionError(instruction)

def interrupt_response(cpu, nmi, ack=None):
    """Called to generate the new pipeline set up to respond to an interrupt."""
    if ack is not None:
        ds = ack(cpu)
    else:
        ds = ( x for x in [] )


    if nmi:
        cpu.most_recent_instruction = "NMI"
        return [ IO(5, True, action=inta(ds))().setcpu(cpu), SW(source="PCH")().setcpu(cpu), SW(source="PCL", action=JP(0x0066))().setcpu(cpu) ]
    if cpu.interrupt_mode == 0:
        cpu.most_recent_instruction = "INT0"
        return [ OCF(data_source=ds, extra=2)().setcpu(cpu) ]
    elif cpu.interrupt_mode == 1:
        cpu.most_recent_instruction = "INT1"
        return [ IO(7, True, action=inta(ds))().setcpu(cpu), SW(source="PCH")().setcpu(cpu), SW(source="PCL", action=JP(0x0038))().setcpu(cpu) ]
    elif cpu.interrupt_mode == 2:
        cpu.most_recent_instruction = "INT2"
        return [ IO(4, True)().setcpu(cpu),
                 OD(action=RRr("address", value=lambda state,v: (state.cpu.reg.I << 8) | (v&0xFE)))().setcpu(cpu).set_data_source(ds),
                 SW(source="PCH")().setcpu(cpu),
                 SW(source="PCL")().setcpu(cpu),
                 MR()().setcpu(cpu),
                 MR(action=JP())().setcpu(cpu) ]
    else:
        raise Exception("Not implemented yet")

def disassemble_instructions(_instructions):
    instructions = [ _ for _ in _instructions ]
    ret = []
    while len(instructions) > 0:
        if instructions[0] in INSTRUCTION_STATES:
            try:
                (code, length) = INSTRUCTION_STATES[instructions[0]][3:]
            except:
                print("Error trying to disassemble 0x{:02X}".format(instructions[0]))
                raise
            if length == 0:
                if len(instructions) > 1:
                    if (instructions[0], instructions[1]) in INSTRUCTION_STATES:
                        try:
                            (code, length) = INSTRUCTION_STATES[(instructions[0], instructions[1])][3:]
                        except:
                            print("Error trying to disassemble (0x{:02X}, 0x{:02X})".format(instructions[0], instructions[1]))
                            raise
                        if length == 0:
                            if len(instructions) > 3:
                                if (instructions[0], instructions[1], instructions[3]) in INSTRUCTION_STATES:
                                    try:
                                        (code, length) = INSTRUCTION_STATES[(instructions[0], instructions[1], instructions[3])][3:]
                                    except:
                                        print("Error trying to disassemble (0x{:02X}, 0x{:02X}, 0x{:02X})".format(instructions[0], instructions[1], instructions[3]))
                                        raise
                                else:
                                    (code, length) = ("???", 4)
                            else:
                                (code, length) = ("???", 4)
                    else:
                        (code, length) = ("???", 2)
                else:
                    (code, length) = ("???", 2)
        else:
            (code, length) = ("???", "1")

        if "nn" in code and length <= len(instructions):
            data = (instructions[length-1] << 8) + instructions[length-2]
            code = code.replace("nn", "0x{:04X}".format(data))
        elif "n" in code and length <= len(instructions):
            data = instructions[length-1]
            code = code.replace("n", "0x{:02X}".format(data))
        if "+d" in code and 3 <= len(instructions):
            data = instructions[2]
            code = code.replace("+d", "+0x{:02X}".format(data))

        for i in range(0,length):
            if len(instructions) > 0:
                instructions.pop(0)
        ret.append((code, length))
    return ret
