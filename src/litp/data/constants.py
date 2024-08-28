LIVE_MODEL_ID = u"LIVE"
LAST_SUCCESSFUL_PLAN_MODEL_ID = u"LAST_SUCCESSFUL_PLAN"
CURRENT_PLAN_ID = u"CURRENT"
SNAPSHOT_PLAN_MODEL_ID_PREFIX = u"SNAPSHOT_"

E_MULTIPLE_CURRENTS = 151
E_MULTIPLE_HEADS = 152
E_NOTHING_APPLIED = 153
E_UPGRADE_REQUIRED = 154
E_NO_MODEL = 155
E_MODEL_EXISTS = 156

E_NO_LEGACY_STORE = 161
E_LEGACY_STORE_EXISTS = 162


if __name__ == '__main__':
    import sys
    d = {
        'E_MULTIPLE_CURRENTS': E_MULTIPLE_CURRENTS,
        'E_MULTIPLE_HEADS': E_MULTIPLE_HEADS,
        'E_NOTHING_APPLIED': E_NOTHING_APPLIED,
        'E_UPGRADE_REQUIRED': E_UPGRADE_REQUIRED,
        'E_NO_MODEL': E_NO_MODEL,
        'E_MODEL_EXISTS': E_MODEL_EXISTS,
        'E_NO_LEGACY_STORE': E_NO_LEGACY_STORE,
        'E_LEGACY_STORE_EXISTS': E_LEGACY_STORE_EXISTS,
    }
    if len(sys.argv) == 2:
        c = sys.argv[1]
        if c in d:
            print d[c]
            sys.exit(0)
        else:
            print >>sys.stderr, "Not Found"
            sys.exit(1)
    else:
        print >>sys.stderr, "Usage: python -m litp.data.constants <CONSTANT>"
        sys.exit(1)
