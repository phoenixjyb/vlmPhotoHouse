# Place catalogue proposal

This is a small, configured starter for the existing reviewed-rectangle flow.
Every rectangle is an approximate search region (`近似范围 / Approx.`), not an
administrative boundary. GPS matching remains local on Windows; this file has
no private-library coordinates.

## Included extents

| ID | Place | Source and source extent |
|---:|---|---|
| 1 | Beijing | [Beijing government emergency-management page](https://yjglj.beijing.gov.cn/art/2012/7/24/art_6162_457440.html): 115°20′–117°30′E, 39°28′–41°05′N. This is the existing configured rectangle, converted to decimal degrees. |
| 2 | Tianjin | [Tianjin government](https://www.tj.gov.cn/sq/tjgk/zrdl/dlwz/): 116°43′–118°04′E, 38°34′–40°15′N. |
| 3 | Guangzhou | [Guangzhou government / Guangzhou Yearbook](https://www.gz.gov.cn/zlgz/gzgk/zrdl/content/post_5725003.html): 112°57′–114°03′E, 22°26′–23°56′N. |
| 4 | Shenzhen | [Shenzhen government](https://www.sz.gov.cn/cn/zjsz/gl/content/post_12318788.html): 113°43′–114°38′E, 22°24′–22°52′N. |
| 5 | Chengdu | [Ministry of Ecology and Environment public document](https://www.mee.gov.cn/ywdt/gsgg/gongshi/wqgs_1/202510/W020251011570084473852.pdf): 102°54′–104°53′E, 30°05′–31°26′N. |
| 101 | Beijing Haidian District | [Haidian district government](https://zyk.bjhd.gov.cn/kjhd/hdgk/202206/t20220613_4530231.shtml): 116°02′31″–116°23′17″E, 39°53′06″–40°09′34″N. The label and aliases include Beijing because “海淀/Haidian” is a district rather than a standalone city. |
| 201 | Chaoyang City, Liaoning | [Chaoyang Agriculture and Rural Affairs Bureau](https://nyncj.chaoyang.gov.cn/html/CYSNW/201401/0162615020378381.html): 118°50′–121°17′E, 40°25′–42°22′N. The label and aliases include Liaoning because “朝阳/Chaoyang” is ambiguous with Beijing Chaoyang District. |

## Additional verified extents

- Shanghai (ID6): [Shanghai government geography](https://english.shanghai.gov.cn/en-Overview/20231209/705180b43f794c1ca43f4d1ddaa049a2.html), 120°51′–122°12′E, 30°40′–31°53′N.
- Beijing Chaoyang District (ID102): [district government](https://www.bjchy.gov.cn/chaoyang/), 116°21′–116°38′E, 39°49′–40°05′N.

## Schema/usage constraints

- `id` values are stable numeric IDs reserved for this starter catalogue;
  they are not GeoNames or government codes.
- All `label` values explicitly say approximate. `aliases` contain both Chinese
  and English forms and are capped at eight entries per item.
- Bounds are only for suggestion/filtering in the current rectangle contract.
  Do not describe a photo as being inside an official administrative boundary
  based on these rectangles.
- Add a place only after recording an authoritative extent source here. Do not
  import a global gazetteer or call an online geocoder for this starter.
