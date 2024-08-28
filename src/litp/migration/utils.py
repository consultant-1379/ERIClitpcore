

def normalize_version(version):
    normalized_version = []
    release_string = ''
    if version is not None:
        for x in str(version).split("."):
            if x.isdigit():
                normalized_version.append(int(x))
            elif '-' in x:
                for y in str(x).split("-"):
                    if y.isdigit():
                        normalized_version.append(int(y))
                    else:
                        release_string = y
            else:
                normalized_version.append(x)
    while len(normalized_version) < 4:
        normalized_version.append(0)
    if len(normalized_version) < 5:
        normalized_version.append(release_string)
    return normalized_version
