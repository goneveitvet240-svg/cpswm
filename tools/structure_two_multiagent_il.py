"""Read-only IL inspection. Requires isolated dnfile/dncil; never patches a DLL."""

import argparse
import hashlib
import json
from pathlib import Path

import dnfile
from dncil.cil.body.reader import read_method_body_from_bytes
from dncil.clr.token import StringToken, Token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assembly", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    pe = dnfile.dnPE(str(args.assembly))
    owners = {}
    for row in pe.net.mdtables.TypeDef.rows:
        for method in row.MethodList:
            owners[id(method.row)] = str(row.TypeName)

    def resolve(value):
        if isinstance(value, StringToken):
            return str(pe.net.user_strings.get(value.rid))
        if isinstance(value, Token):
            row = pe.net.mdtables.tables[value.table].rows[value.rid - 1]
            return (
                owners.get(id(row), "")
                + "."
                + str(getattr(row, "Name", getattr(row, "TypeName", type(row).__name__)))
            )
        return str(value)

    selected = []
    for row in pe.net.mdtables.TypeDef.rows:
        name = str(row.TypeName)
        wanted = (
            {
                "Initialize",
                "addAgents",
                "SetUpPhysicsController",
                "createAgentType",
                "ProcessControlCommand",
            }
            if name == "AgentManager"
            else {"ProcessControlCommand", "actionFinished", "Initialize"}
            if name == "BaseFPSAgentController"
            else set()
        )
        for method in row.MethodList:
            method = method.row
            if str(method.Name) not in wanted or not method.Rva:
                continue
            body = read_method_body_from_bytes(pe.get_data(method.Rva))
            selected.append(
                {
                    "type": name,
                    "method": str(method.Name),
                    "rva": method.Rva,
                    "il_sha256": hashlib.sha256(body.raw_bytes).hexdigest(),
                    "instructions": [
                        {
                            "offset": ins.offset,
                            "opcode": str(ins.opcode),
                            "operand": resolve(ins.operand),
                        }
                        for ins in body.instructions
                    ],
                    "exception_handlers": [
                        {
                            "try_start": h.try_start,
                            "try_end": h.try_end,
                            "handler_start": h.handler_start,
                            "handler_end": h.handler_end,
                            "catch_type": resolve(h.catch_type),
                        }
                        for h in body.exception_handlers
                    ],
                }
            )
    report = {
        "assembly_sha256": hashlib.sha256(args.assembly.read_bytes()).hexdigest(),
        "assembly": str(args.assembly.resolve()),
        "inspection_only": True,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "methods": selected,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({"assembly_sha256": report["assembly_sha256"], "methods": len(selected)}))


if __name__ == "__main__":
    main()
