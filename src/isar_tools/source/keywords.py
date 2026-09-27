"""Outer-syntax command keywords and their kinds.

Isabelle decides lexically whether a token is a command: a word that is a
declared command keyword always starts a new command. The declarations come
from theory headers (``keywords "foo" :: thy_decl``) along the import chain.
Without running Isabelle we cannot see the headers of the Pure and HOL theories,
so this module carries a built-in table of their commands. Headers of the
analyzed project are added on top (see ``isar_tools.source.theory``).

Kind names are Isabelle's own (``Pure/Isar/keyword.ML``), so a header
declaration maps onto them without translation.
"""

from enum import StrEnum


class CommandKind(StrEnum):
    DIAG = "diag"
    DOCUMENT_HEADING = "document_heading"
    DOCUMENT_BODY = "document_body"
    DOCUMENT_RAW = "document_raw"
    THY_BEGIN = "thy_begin"
    THY_END = "thy_end"
    THY_DECL = "thy_decl"
    THY_DECL_BLOCK = "thy_decl_block"
    THY_DEFN = "thy_defn"
    THY_STMT = "thy_stmt"
    THY_LOAD = "thy_load"
    THY_GOAL = "thy_goal"
    THY_GOAL_DEFN = "thy_goal_defn"
    THY_GOAL_STMT = "thy_goal_stmt"
    QED = "qed"
    QED_SCRIPT = "qed_script"
    QED_BLOCK = "qed_block"
    QED_GLOBAL = "qed_global"
    PRF_GOAL = "prf_goal"
    PRF_BLOCK = "prf_block"
    NEXT_BLOCK = "next_block"
    PRF_OPEN = "prf_open"
    PRF_CLOSE = "prf_close"
    PRF_CHAIN = "prf_chain"
    PRF_DECL = "prf_decl"
    PRF_ASM = "prf_asm"
    PRF_ASM_GOAL = "prf_asm_goal"
    PRF_SCRIPT = "prf_script"
    PRF_SCRIPT_GOAL = "prf_script_goal"
    PRF_SCRIPT_ASM_GOAL = "prf_script_asm_goal"
    BEFORE_COMMAND = "before_command"
    QUASI_COMMAND = "quasi_command"


K = CommandKind
# `str in CommandKind` raises TypeError before Python 3.12.
KIND_NAMES = frozenset(kind.value for kind in CommandKind)

# Theory-level commands that state a goal needing a proof.
THEORY_GOALS = frozenset({K.THY_GOAL, K.THY_GOAL_DEFN, K.THY_GOAL_STMT})
# Proof commands that state a goal needing its own proof.
PROOF_GOALS = frozenset({K.PRF_GOAL, K.PRF_ASM_GOAL, K.PRF_SCRIPT_GOAL, K.PRF_SCRIPT_ASM_GOAL})
# Commands that finish the innermost open goal.
PROOF_TERMINATORS = frozenset({K.QED, K.QED_SCRIPT, K.QED_BLOCK})
DOCUMENT = frozenset({K.DOCUMENT_HEADING, K.DOCUMENT_BODY, K.DOCUMENT_RAW})
# Every kind that is only valid inside a proof.
PROOF_KINDS = frozenset(
    {
        K.QED,
        K.QED_SCRIPT,
        K.QED_BLOCK,
        K.QED_GLOBAL,
        K.PRF_GOAL,
        K.PRF_BLOCK,
        K.NEXT_BLOCK,
        K.PRF_OPEN,
        K.PRF_CLOSE,
        K.PRF_CHAIN,
        K.PRF_DECL,
        K.PRF_ASM,
        K.PRF_ASM_GOAL,
        K.PRF_SCRIPT,
        K.PRF_SCRIPT_GOAL,
        K.PRF_SCRIPT_ASM_GOAL,
    }
)


def _table(spec: dict[CommandKind, str]) -> dict[str, CommandKind]:
    table: dict[str, CommandKind] = {}
    for kind, names in spec.items():
        for name in names.split():
            table[name] = kind
    return table


# Commands of Pure and of the HOL session images (Main, HOL-Library, and the
# commonly used tools). Hand-maintained; extend when a corpus shows a gap.
BUILTIN_COMMANDS: dict[str, CommandKind] = _table(
    {
        K.THY_BEGIN: "theory",
        K.THY_END: "end",
        K.DOCUMENT_HEADING: "chapter section subsection subsubsection paragraph subparagraph",
        K.DOCUMENT_BODY: "text txt",
        K.DOCUMENT_RAW: "text_raw",
        K.THY_LOAD: (
            "ML_file ML_file_debug ML_file_no_debug SML_file SML_file_debug "
            "SML_file_no_debug external_file bibtex_file generate_file"
        ),
        K.THY_DECL: (
            "ML ML_command ML_export ML_val SML_import SML_export setup local_setup "
            "attribute_setup method_setup simproc_setup declaration syntax_declaration "
            "parse_ast_translation parse_translation print_translation "
            "typed_print_translation print_ast_translation oracle default_sort typedecl "
            "type_synonym nonterminal judgment consts syntax no_syntax translations "
            "no_translations axiomatization alias type_alias type_notation no_type_notation "
            "notation no_notation declare hide_class hide_type hide_const hide_fact "
            "named_theorems unbundle lemmas theorems abbreviation "
            "inductive coinductive inductive_set coinductive_set inductive_cases "
            "inductive_simps fun primrec primcorec partial_function datatype codatatype "
            "datatype_compat record case_of_simps simps_of_case setup_lifting "
            "lifting_forget lifting_update code_datatype code_printing code_identifier "
            "code_reflect code_reserved export_code quickcheck_params nitpick_params "
            "refute_params sledgehammer_params adhoc_overloading no_adhoc_overloading "
            "bnf_axiomatization compile_generated_files export_generated_files syntax_consts "
            "quickcheck_generator"
        ),
        K.THY_DECL_BLOCK: (
            "context locale class instantiation overloading notepad bundle experiment open_bundle"
        ),
        K.THY_DEFN: "definition",
        K.THY_GOAL: (
            "instance subclass interpretation global_interpretation sublocale typedef "
            "function termination quotient_type quotient_definition specification "
            "lift_definition code_pred free_constructors functor bnf primcorecursive"
        ),
        K.THY_GOAL_STMT: "lemma theorem corollary proposition schematic_goal",
        K.DIAG: (
            "value term typ prop thm print_state print_statement print_syntax "
            "print_abbrevs print_defn_rules print_attributes print_methods print_rules "
            "print_induct_rules print_simpset print_facts print_cases print_term_bindings "
            "print_binds print_options print_commands print_codesetup print_codeproc "
            "print_dependencies print_interps print_bundles print_case_translations "
            "print_quotients print_quotmaps print_quotconsts print_record print_inductives "
            "print_ML_antiquotations print_antiquotations print_bnfs print_theorems "
            "print_locale print_locales print_classes print_context find_consts "
            "find_theorems thm_deps sledgehammer nitpick quickcheck refute try try0 "
            "solve_direct find_unused_assms unused_thms help locale_deps class_deps "
            "code_thms full_prf prf values"
        ),
        K.QED: "by . .. sorry \\<proof>",
        K.QED_SCRIPT: "done",
        K.QED_BLOCK: "qed",
        K.QED_GLOBAL: "oops",
        K.PRF_GOAL: "have show hence thus consider interpret",
        K.PRF_BLOCK: "proof",
        K.NEXT_BLOCK: "next",
        K.PRF_OPEN: "{",
        K.PRF_CLOSE: "}",
        K.PRF_CHAIN: "then from with finally ultimately",
        K.PRF_DECL: "using unfolding note let write ML_prf supply include including also moreover",
        K.PRF_ASM: "assume presume fix define case",
        K.PRF_ASM_GOAL: "obtain guess",
        K.PRF_SCRIPT: "apply apply_end prefer defer back",
        K.PRF_SCRIPT_GOAL: "subgoal",
        K.BEFORE_COMMAND: "private qualified",
    }
)


# Commands of distribution theories outside Main, active only in theories that
# import them (directly or through a project theory). Keys are a theory's
# qualified name or, for a whole session, the session name.
IMPORTED_COMMANDS: dict[str, dict[str, CommandKind]] = {
    "HOLCF": _table({K.THY_DECL: "fixrec domain domaindef", K.THY_GOAL: "pcpodef cpodef"}),
    "HOL-Eisbach": _table({K.THY_DECL: "method"}),
    "HOL-Nominal": _table(
        {
            K.THY_DECL: "atom_decl nominal_datatype equivariance",
            K.THY_GOAL: "nominal_primrec nominal_inductive nominal_inductive2",
        }
    ),
    "HOL-Library.BNF_Corec": _table(
        {K.THY_DECL: "corec coinduction_upto", K.THY_GOAL: "corecursive friend_of_corec"}
    ),
    "HOL-Library.Time_Commands": _table({K.THY_DECL: "time_fun time_definition time_function"}),
    "HOL-Library.Conditional_Parametricity": _table({K.THY_DECL: "parametric_constant"}),
}


def commands_of_import(name: str) -> dict[str, CommandKind]:
    """Commands an import of a distribution theory makes available.

    ``name`` is an import as written, e.g. ``HOLCF``, ``"HOL-Eisbach.Eisbach"``,
    or ``"HOL-Library.Time_Commands"``.
    """
    return {
        **IMPORTED_COMMANDS.get(name.split(".", 1)[0], {}),
        **IMPORTED_COMMANDS.get(name, {}),
    }
