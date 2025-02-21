# pylint: disable=import-outside-toplevel
"""A collection of particle info containers.

The :mod:`.particle` module is the starting point of `qrules`. Its main
interface is the `ParticleCollection`, which is a collection of immutable
`Particle` instances that are uniquely defined by their properties. As such, it
can be used stand-alone as a database of quantum numbers (see
:doc:`/usage/particle`).

The `.transition` module uses the properties of `Particle` instances when it
computes which `.MutableTransition` s are allowed between an initial state
and final state.
"""

import logging
import re
from collections import abc
from difflib import get_close_matches
from functools import total_ordering
from math import copysign
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    SupportsFloat,
    Tuple,
    Union,
)

import attrs
from attrs import field, frozen
from attrs.converters import optional
from attrs.validators import instance_of

from .conservation_rules import GellMannNishijimaInput, gellmann_nishijima
from .quantum_numbers import Parity, _to_fraction

if TYPE_CHECKING:
    from particle import Particle as PdgDatabase
    from particle.particle import enums

    try:
        from IPython.lib.pretty import PrettyPrinter
    except ImportError:
        PrettyPrinter = Any


def _to_float(value: SupportsFloat) -> float:
    float_value = float(value)
    if float_value == -0.0:
        float_value = 0.0
    return float_value


@total_ordering
@frozen(eq=False, hash=True, order=False)
class Spin:
    """Safe, immutable data container for spin **with projection**."""

    magnitude: float = field(converter=_to_float)
    projection: float = field(converter=_to_float)

    def __attrs_post_init__(self) -> None:
        if self.magnitude % 0.5 != 0.0:
            raise ValueError(
                f"Spin magnitude {self.magnitude} has to be a multitude of 0.5"
            )
        if abs(self.projection) > self.magnitude:
            if self.magnitude < 0.0:
                raise ValueError(
                    "Spin magnitude has to be positive, but is"
                    f" {self.magnitude}"
                )
            raise ValueError(
                "Absolute value of spin projection cannot be larger than its "
                "magnitude:\n"
                f" abs({self.projection}) > {self.magnitude}"
            )
        if not (self.projection - self.magnitude).is_integer():
            raise ValueError(
                f"{type(self).__name__}{(self.magnitude, self.projection)}:"
                " (projection - magnitude) should be integer"
            )

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Spin):
            return (
                self.magnitude == other.magnitude
                and self.projection == other.projection
            )
        return self.magnitude == other

    def __float__(self) -> float:
        return self.magnitude

    def __gt__(self, other: Any) -> bool:
        if isinstance(other, Spin):
            return attrs.astuple(self) > attrs.astuple(other)
        return self.magnitude > other

    def __neg__(self) -> "Spin":
        return Spin(self.magnitude, -self.projection)

    def __repr__(self) -> str:
        return f"{type(self).__name__}{(self.magnitude, self.projection)}"

    def _repr_pretty_(self, p: "PrettyPrinter", _: bool) -> None:
        class_name = type(self).__name__
        magnitude = _to_fraction(self.magnitude)
        projection = _to_fraction(self.projection, render_plus=True)
        p.text(f"{class_name}({magnitude}, {projection})")


def _to_parity(value: Union[Parity, int]) -> Parity:
    return Parity(int(value))


def _to_spin(value: Union[Spin, Tuple[float, float]]) -> Spin:
    if isinstance(value, tuple):
        return Spin(*value)
    return value


@total_ordering
@frozen(kw_only=True, order=False, repr=True)
class Particle:  # pylint: disable=too-many-instance-attributes
    """Immutable container of data defining a physical particle.

    A `Particle` is defined by the minimum set of the quantum numbers that
    every possible instances of that particle have in common (the "static"
    quantum numbers of the particle). A "non-static" quantum number is the spin
    projection. Hence `Particle` instances do **not** contain spin projection
    information.

    `Particle` instances are uniquely defined by their quantum numbers and
    properties like `~Particle.mass`. The `~Particle.name` and `~Particle.pid`
    are therefore just labels that are not taken into account when checking if
    two `Particle` instances are equal.

    .. note:: As opposed to classes such as `.EdgeQuantumNumbers` and
        `.NodeQuantumNumbers`, the `Particle` class serves as an interface to
        the user (see :doc:`/usage/particle`).
    """

    # Labels
    name: str = field(eq=False)
    pid: int = field(eq=False)
    latex: Optional[str] = field(eq=False, default=None)
    # Unique properties
    spin: float = field(converter=float)
    mass: float = field(converter=float)
    width: float = field(converter=float, default=0.0)
    charge: int = field(default=0)
    isospin: Optional[Spin] = field(converter=optional(_to_spin), default=None)
    strangeness: int = field(default=0, validator=instance_of(int))
    charmness: int = field(default=0, validator=instance_of(int))
    bottomness: int = field(default=0, validator=instance_of(int))
    topness: int = field(default=0, validator=instance_of(int))
    baryon_number: int = field(default=0, validator=instance_of(int))
    electron_lepton_number: int = field(default=0, validator=instance_of(int))
    muon_lepton_number: int = field(default=0, validator=instance_of(int))
    tau_lepton_number: int = field(default=0, validator=instance_of(int))
    parity: Optional[Parity] = field(
        converter=optional(_to_parity), default=None
    )
    c_parity: Optional[Parity] = field(
        converter=optional(_to_parity), default=None
    )
    g_parity: Optional[Parity] = field(
        converter=optional(_to_parity), default=None
    )

    def __attrs_post_init__(self) -> None:
        if self.isospin is not None and not gellmann_nishijima(
            GellMannNishijimaInput(
                charge=self.charge,
                isospin_projection=self.isospin.projection
                if self.isospin
                else None,
                strangeness=self.strangeness,
                charmness=self.charmness,
                bottomness=self.bottomness,
                topness=self.topness,
                baryon_number=self.baryon_number,
                electron_lepton_number=self.electron_lepton_number,
                muon_lepton_number=self.muon_lepton_number,
                tau_lepton_number=self.tau_lepton_number,
            )
        ):
            raise ValueError(
                f"Cannot construct particle {self.name}, because its quantum"
                " numbers don't agree with the Gell-Mann–Nishijima formula:\n"
                f"  Q[{self.charge}] != "
                f"Iz[{self.isospin.projection if self.isospin else 0}] + 1/2 "
                f"(B[{self.baryon_number}] + "
                f" S[{self.strangeness}] + "
                f" C[{self.charmness}] +"
                f" B'[{self.bottomness}] +"
                f" T[{self.strangeness}]"
                ")"
            )

    def __gt__(self, other: Any) -> bool:
        if isinstance(other, Particle):

            def sorting_key(particle: Particle) -> tuple:
                name_root = _get_name_root(particle.name)
                return (
                    name_root[0].lower(),
                    name_root,
                    particle.mass,
                    particle.charge,
                )

            return sorting_key(self) > sorting_key(other)
        raise NotImplementedError(
            f"Cannot compare {type(self).__name__} with {type(other).__name__}"
        )

    def __neg__(self) -> "Particle":
        return create_antiparticle(self)

    def is_lepton(self) -> bool:
        return (
            self.electron_lepton_number != 0
            or self.muon_lepton_number != 0
            or self.tau_lepton_number != 0
        )

    def _repr_pretty_(self, p: "PrettyPrinter", cycle: bool) -> None:
        class_name = type(self).__name__
        if cycle:
            p.text(f"{class_name}(...)")
        else:
            with p.group(indent=2, open=f"{class_name}("):
                for attribute in attrs.fields(type(self)):
                    value = getattr(self, attribute.name)
                    if value != attribute.default:
                        p.breakable()
                        p.text(f"{attribute.name}=")
                        if isinstance(value, Parity):
                            p.text(_to_fraction(int(value), render_plus=True))
                        else:
                            p.pretty(value)
                        p.text(",")
            p.breakable()
            p.text(")")


def _get_name_root(name: str) -> str:
    """Strip a string (particularly the `.Particle.name`) of specifications."""
    name_root = name
    name_root = re.sub(r"\(.+\)", "", name_root)
    name_root = re.sub(r"[\*\+\-~\d']", "", name_root)
    return name_root


ParticleWithSpin = Tuple[Particle, float]


class ParticleCollection(abc.MutableSet):
    """Searchable collection of immutable `.Particle` instances."""

    def __init__(self, particles: Optional[Iterable[Particle]] = None) -> None:
        self.__particles: Dict[str, Particle] = {}
        self.__pid_to_name: Dict[int, str] = {}
        if particles is not None:
            self.update(particles)

    def __contains__(self, instance: object) -> bool:
        if isinstance(instance, str):
            return instance in self.__particles
        if isinstance(instance, Particle):
            return instance in self.__particles.values()
        if isinstance(instance, int):
            return instance in self.__pid_to_name
        raise NotImplementedError(
            f"Cannot search for type {type(instance).__name__}"
        )

    def __eq__(self, other: object) -> bool:
        if isinstance(other, abc.Iterable):
            return set(self) == set(other)
        raise NotImplementedError(
            f"Cannot compare {type(self).__name__} with  {type(self).__name__}"
        )

    def __getitem__(self, particle_name: str) -> Particle:
        if particle_name in self.__particles:
            return self.__particles[particle_name]
        error_message = (
            f"No particle with name '{particle_name}' in the database"
        )
        candidates = [
            p.name
            for p in sorted(self, key=lambda p: p.mass)
            if p.name.startswith(particle_name)
        ]
        if not candidates:
            candidates = get_close_matches(particle_name, self.names, n=5)
        if len(candidates) == 1:
            error_message += f". Did you mean '{candidates[0]}'?"
        elif len(candidates) > 1:
            error_message += f". Did you mean one of these? {candidates}"
        raise KeyError(error_message)

    def __iter__(self) -> Iterator[Particle]:
        return self.__particles.values().__iter__()

    def __len__(self) -> int:
        return len(self.__particles)

    def __iadd__(
        self, other: Union[Particle, "ParticleCollection"]
    ) -> "ParticleCollection":
        if isinstance(other, Particle):
            self.add(other)
        elif isinstance(other, ParticleCollection):
            self.update(other)
        else:
            raise NotImplementedError(f"Cannot add {type(other).__name__}")
        return self

    def __repr__(self) -> str:
        output = f"{type(self).__name__}({{"
        for particle in self:
            output += f"\n    {particle},"
        output += "})"
        return output

    def _repr_pretty_(self, p: "PrettyPrinter", cycle: bool) -> None:
        class_name = type(self).__name__
        if cycle:
            p.text(f"{class_name}(...)")
        else:
            with p.group(indent=2, open=f"{class_name}({{"):
                for particle in self:
                    p.breakable()
                    p.pretty(particle)
                    p.text(",")
            p.breakable()
            p.text("})")

    def add(self, value: Particle) -> None:
        if value in self.__particles.values():
            equivalent_particles = {p for p in self if p == value}
            equivalent_particle = next(iter(equivalent_particles))
            raise ValueError(
                f'Added particle "{value.name}" is equivalent to '
                f'existing particle "{equivalent_particle.name}"',
            )
        if value.name in self.__particles:
            logging.warning(f'Overwriting particle with name "{value.name}"')
        if value.pid in self.__pid_to_name:
            logging.warning(
                f"Particle with PID {value.pid} already exists:"
                f' "{self.find(value.pid).name}"'
            )
        self.__particles[value.name] = value
        self.__pid_to_name[value.pid] = value.name

    def discard(self, value: Union[Particle, str]) -> None:
        particle_name = ""
        if isinstance(value, Particle):
            particle_name = value.name
        elif isinstance(value, str):
            particle_name = value
        else:
            raise NotImplementedError(
                f"Cannot discard something of type {type(value).__name__}"
            )
        del self.__pid_to_name[self[particle_name].pid]
        del self.__particles[particle_name]

    def find(self, search_term: Union[int, str]) -> Particle:
        """Search for a particle by either name (`str`) or PID (`int`)."""
        if isinstance(search_term, str):
            particle_name = search_term
            return self.__getitem__(particle_name)
        if isinstance(search_term, int):
            if search_term not in self.__pid_to_name:
                raise KeyError(f"No particle with PID {search_term}")
            particle_name = self.__pid_to_name[search_term]
            return self.__getitem__(particle_name)
        raise NotImplementedError(
            f"Cannot search for a search term of type {type(search_term)}"
        )

    def filter(  # noqa: A003
        self, function: Callable[[Particle], bool]
    ) -> "ParticleCollection":
        """Search by `Particle` properties using a :code:`lambda` function.

        For example:

        >>> from qrules.particle import load_pdg
        >>> pdg = load_pdg()
        >>> subset = pdg.filter(
        ...     lambda p: p.mass > 1.8
        ...     and p.mass < 2.0
        ...     and p.spin == 2
        ...     and p.strangeness == 1
        ... )
        >>> sorted(list(subset.names))
        ['K(2)(1820)+', 'K(2)(1820)0', 'K(2)*(1980)+', 'K(2)*(1980)0']
        """
        return ParticleCollection(
            {particle for particle in self if function(particle)}
        )

    def update(self, other: Iterable[Particle]) -> None:
        if not isinstance(other, abc.Iterable):
            raise TypeError(
                f"Cannot update {type(self).__name__} from "
                f"non-iterable class {type(self).__name__}"
            )
        for particle in other:
            self.add(particle)

    @property
    def names(self) -> List[str]:
        return [p.name for p in sorted(self)]


def create_particle(  # pylint: disable=too-many-arguments,too-many-locals
    template_particle: Particle,
    name: Optional[str] = None,
    latex: Optional[str] = None,
    pid: Optional[int] = None,
    mass: Optional[float] = None,
    width: Optional[float] = None,
    charge: Optional[int] = None,
    spin: Optional[float] = None,
    isospin: Optional[Spin] = None,
    strangeness: Optional[int] = None,
    charmness: Optional[int] = None,
    bottomness: Optional[int] = None,
    topness: Optional[int] = None,
    baryon_number: Optional[int] = None,
    electron_lepton_number: Optional[int] = None,
    muon_lepton_number: Optional[int] = None,
    tau_lepton_number: Optional[int] = None,
    parity: Optional[int] = None,
    c_parity: Optional[int] = None,
    g_parity: Optional[int] = None,
) -> Particle:
    return Particle(
        name=name if name else template_particle.name,
        pid=pid if pid else template_particle.pid,
        latex=latex if latex else template_particle.latex,
        mass=mass if mass is not None else template_particle.mass,
        width=width if width else template_particle.width,
        spin=spin if spin else template_particle.spin,
        charge=charge if charge else template_particle.charge,
        strangeness=strangeness
        if strangeness
        else template_particle.strangeness,
        charmness=charmness if charmness else template_particle.charmness,
        bottomness=bottomness if bottomness else template_particle.bottomness,
        topness=topness if topness else template_particle.topness,
        baryon_number=baryon_number
        if baryon_number
        else template_particle.baryon_number,
        electron_lepton_number=electron_lepton_number
        if electron_lepton_number
        else template_particle.electron_lepton_number,
        muon_lepton_number=muon_lepton_number
        if muon_lepton_number
        else template_particle.muon_lepton_number,
        tau_lepton_number=tau_lepton_number
        if tau_lepton_number
        else template_particle.tau_lepton_number,
        isospin=template_particle.isospin
        if isospin is None
        else template_particle.isospin,
        parity=template_particle.parity if parity is None else Parity(parity),
        c_parity=template_particle.c_parity
        if c_parity is None
        else Parity(c_parity),
        g_parity=template_particle.g_parity
        if g_parity is None
        else Parity(g_parity),
    )


def create_antiparticle(
    template_particle: Particle,
    new_name: Optional[str] = None,
    new_latex: Optional[str] = None,
) -> Particle:
    isospin: Optional[Spin] = None
    if template_particle.isospin:
        isospin = -template_particle.isospin
    parity: Optional[Parity] = None
    if template_particle.parity is not None:
        if template_particle.spin.is_integer():
            parity = template_particle.parity
        else:
            parity = -template_particle.parity
    return Particle(
        name=new_name if new_name else "anti-" + template_particle.name,
        pid=-template_particle.pid,
        latex=new_latex
        if new_latex
        else Rf"\overline{{{template_particle.latex}}}",
        mass=template_particle.mass,
        width=template_particle.width,
        charge=-template_particle.charge,
        spin=template_particle.spin,
        isospin=isospin,
        strangeness=-template_particle.strangeness,
        charmness=-template_particle.charmness,
        bottomness=-template_particle.bottomness,
        topness=-template_particle.topness,
        baryon_number=-template_particle.baryon_number,
        electron_lepton_number=-template_particle.electron_lepton_number,
        muon_lepton_number=-template_particle.muon_lepton_number,
        tau_lepton_number=-template_particle.tau_lepton_number,
        parity=parity,
        c_parity=template_particle.c_parity,
        g_parity=template_particle.g_parity,
    )


def load_pdg() -> ParticleCollection:
    """Create a `.ParticleCollection` with all entries from the PDG.

    PDG info is imported from the `scikit-hep/particle
    <https://github.com/scikit-hep/particle>`_ package.
    """
    from particle import Particle as PdgDatabase

    all_pdg_particles = PdgDatabase.findall(
        lambda item: item.charge is not None
        and item.charge.is_integer()  # remove quarks
        and item.J is not None  # remove new physics and nuclei
        and abs(item.pdgid) < 1e9  # p and n as nucleus
        and item.name not in __skip_particles
        and not (item.mass is None and not item.name.startswith("nu"))
    )
    particle_collection = ParticleCollection()
    for pdg_particle in all_pdg_particles:
        new_particle = __convert_pdg_instance(pdg_particle)
        particle_collection.add(new_particle)
    return particle_collection


__skip_particles = {
    "K(L)0",  # no isospin projection
    "K(S)0",  # no isospin projection
    "B(s2)*(5840)0",  # isospin(0.5, 0.0) ?
    "B(s2)*(5840)~0",  # isospin(0.5, 0.0) ?
}


def __sign(value: Union[float, int]) -> int:
    return int(copysign(1, value))


# cspell:ignore pdgid
def __convert_pdg_instance(pdg_particle: "PdgDatabase") -> Particle:
    def convert_mass_width(value: Optional[float]) -> float:
        if value is None:
            return 0.0
        return float(value) / 1e3  # https://github.com/ComPWA/qrules/issues/14

    if pdg_particle.charge is None:
        raise ValueError(f"PDG instance has no charge:\n{pdg_particle}")
    quark_numbers = __compute_quark_numbers(pdg_particle)
    lepton_numbers = __compute_lepton_numbers(pdg_particle)
    if pdg_particle.pdgid.is_lepton:  # convention: C(fermion)=+1
        parity: Optional[Parity] = Parity(__sign(pdg_particle.pdgid))
    else:
        parity = __create_parity(pdg_particle.P)
    latex = None
    if pdg_particle.latex_name != "Unknown":
        latex = str(pdg_particle.latex_name)
    return Particle(
        name=str(pdg_particle.name),
        latex=latex,
        pid=int(pdg_particle.pdgid),
        mass=convert_mass_width(pdg_particle.mass),
        width=convert_mass_width(pdg_particle.width),
        charge=int(pdg_particle.charge),
        spin=float(pdg_particle.J),
        strangeness=quark_numbers[0],
        charmness=quark_numbers[1],
        bottomness=quark_numbers[2],
        topness=quark_numbers[3],
        baryon_number=__compute_baryonnumber(pdg_particle),
        electron_lepton_number=lepton_numbers[0],
        muon_lepton_number=lepton_numbers[1],
        tau_lepton_number=lepton_numbers[2],
        isospin=__create_isospin(pdg_particle),
        parity=parity,
        c_parity=__create_parity(pdg_particle.C),
        g_parity=__create_parity(pdg_particle.G),
    )


def __compute_quark_numbers(
    pdg_particle: "PdgDatabase",
) -> Tuple[int, int, int, int]:
    strangeness = 0
    charmness = 0
    bottomness = 0
    topness = 0
    if pdg_particle.pdgid.is_hadron:
        quark_content = __filter_quark_content(pdg_particle)
        strangeness = quark_content.count("S") - quark_content.count("s")
        charmness = quark_content.count("c") - quark_content.count("C")
        bottomness = quark_content.count("B") - quark_content.count("b")
        topness = quark_content.count("t") - quark_content.count("T")
    return (
        strangeness,
        charmness,
        bottomness,
        topness,
    )


def __compute_lepton_numbers(
    pdg_particle: "PdgDatabase",
) -> Tuple[int, int, int]:
    electron_lepton_number = 0
    muon_lepton_number = 0
    tau_lepton_number = 0
    if pdg_particle.pdgid.is_lepton:
        lepton_number = int(__sign(pdg_particle.pdgid))
        if "e" in pdg_particle.name:
            electron_lepton_number = lepton_number
        elif "mu" in pdg_particle.name:
            muon_lepton_number = lepton_number
        elif "tau" in pdg_particle.name:
            tau_lepton_number = lepton_number
    return electron_lepton_number, muon_lepton_number, tau_lepton_number


def __compute_baryonnumber(pdg_particle: "PdgDatabase") -> int:
    return int(__sign(pdg_particle.pdgid) * pdg_particle.pdgid.is_baryon)


def __create_isospin(pdg_particle: "PdgDatabase") -> Optional[Spin]:
    if pdg_particle.I is None:
        return None
    magnitude = pdg_particle.I
    projection = __isospin_projection_from_pdg(pdg_particle)
    return Spin(magnitude, projection)


def __isospin_projection_from_pdg(pdg_particle: "PdgDatabase") -> float:
    if pdg_particle.charge is None:
        raise ValueError(f"PDG instance has no charge:\n{pdg_particle}")
    if "qq" in pdg_particle.quarks.lower():
        strangeness, charmness, bottomness, topness = __compute_quark_numbers(
            pdg_particle
        )
        baryon_number = __compute_baryonnumber(pdg_particle)
        projection = pdg_particle.charge - 0.5 * (
            baryon_number + strangeness + charmness + bottomness + topness
        )
    else:
        projection = 0.0
        if pdg_particle.pdgid.is_hadron:
            quark_content = __filter_quark_content(pdg_particle)
            projection += quark_content.count("u") + quark_content.count("D")
            projection -= quark_content.count("U") + quark_content.count("d")
            projection *= 0.5
    if (
        pdg_particle.I is not None
        and not (pdg_particle.I - projection).is_integer()
    ):
        raise ValueError(f"Cannot have isospin {(pdg_particle.I, projection)}")
    return projection


def __filter_quark_content(pdg_particle: "PdgDatabase") -> str:
    matches = re.search(r"([dDuUsScCbBtT+-]{2,})", pdg_particle.quarks)
    if matches is None:
        return ""
    return matches[1]


def __create_parity(parity_enum: "enums.Parity") -> Optional[Parity]:
    from particle.particle import enums

    if parity_enum is None or parity_enum == enums.Parity.u:
        return None
    if parity_enum == getattr(parity_enum, "o", None):  # particle < 0.14
        return None
    return Parity(int(parity_enum))
